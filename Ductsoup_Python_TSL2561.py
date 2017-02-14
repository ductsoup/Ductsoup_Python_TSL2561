from __future__ import division
import logging
import time

_COMMAND_BIT             = 0x80
_WORD_BIT                = 0x20
_CLEAR_BIT               = 0x40

_REGISTER_CONTROL        = 0x00
_REGISTER_TIMING         = 0x01
_REGISTER_THRESHHOLD_MIN = 0x02
_REGISTER_THRESHHOLD_MAX = 0x04
_REGISTER_INTERRUPT      = 0x06
_REGISTER_ID             = 0x0A
_REGISTER_CHANNEL0       = 0x0C
_REGISTER_CHANNEL1       = 0x0E

_CONTROL_POWERON         = 0x03
_CONTROL_POWEROFF        = 0x00

_INTERRUPT_NONE          = 0x00
_INTERRUPT_LEVEL         = 0x10

_INTEGRATION_TIME = {
#  time     hex     wait    clip    min     max     scale
    13:     (0x00,  15,     4900,   100,    4850,   0x7517),
    101:    (0x01,  120,    37000,  200,    36000,  0x0FE7),
    402:    (0x02,  450,    65000,  500,    63000,  1 << 10),
    0:      (0x03,  0,      0,      0,      0,      0),
}

# Device states enumerated from most to least sensitive
_HDR = {
  0:{'gain': 16, 'time': 402, 'min':  None, 'max': 62258}, # 6432
  1:{'gain': 16, 'time': 101, 'min':  1859, 'max': 35318}, # 1616
  2:{'gain':  1, 'time': 402, 'min':  3277, 'max': 62258}, #  402
  3:{'gain': 16, 'time':  13, 'min':   252, 'max':  4876}, #  208
  4:{'gain':  1, 'time': 101, 'min':  1859, 'max': 35318}, #  101
  5:{'gain':  1, 'time':  13, 'min':   252, 'max':  None}, #   13
  }

# I2C address options
TSL2561_ADDR_LOW         = 0x29
TSL2561_ADDR_FLOAT       = 0x39 # Default address (pin left floating)
TSL2561_ADDR_HIGH        = 0x49

# Operating powermodes
TSL2561_LOWPOWER = 0
TSL2561_STANDARD = 1

class TSL2561(object):

    _LUX_SCALE = (
       #       K       B       M
           (0x0040, 0x01f2, 0x01be),
           (0x0080, 0x0214, 0x02d1),
           (0x00c0, 0x023f, 0x037b),
           (0x0100, 0x0270, 0x03fe),
           (0x0138, 0x016f, 0x01fc),
           (0x019a, 0x00d2, 0x00fb),
           (0x029a, 0x0018, 0x0012),
       )

    def __init__(self, powermode=TSL2561_STANDARD, address=TSL2561_ADDR_FLOAT, debug=False, i2c=None, **kwargs):
        # Setup logging
        self._logger = logging.getLogger('Ductsoup_TSL.TSL2561')
        if debug:
            logging.basicConfig(format='%(levelname)s: [TSL] %(message)s', level=logging.INFO)

        # Create I2C device
        self.address = address
        if i2c is None:
            import Adafruit_GPIO.I2C as I2C
            i2c = I2C
        self._device = i2c.get_i2c_device(address, **kwargs)

        # Verify device ID
        self.part_no, self.rev_no = self.sensor_id()
        if not self.part_no & 0x01:
            raise RuntimeError("bad sensor id 0x{:x}".format(self.part_no << 4 | self.rev_no))
        else:
            self._logger.info('Device found (partno={0}, revision={1})'.format(self.part_no, self.rev_no))

        # Check and set the power powermode
        if powermode not in [TSL2561_LOWPOWER, TSL2561_STANDARD]:
            raise ValueError('Unexpected powermode value {0}.  Set powermode to TSL2561_LOWPOWER or TSL2561_STANDARD (default)'.format(powermode))
        self._powermode = powermode
        self._logger.info('Device power powermode was set to {0}'.format('normal' if powermode else 'low'))
        self._active = None
        self.active(self._powermode == TSL2561_STANDARD)

        # Set the hdr status, gain and integration time to the power up state
        self._hdr = None 
        self._gain = 1
        self._integration_time = 402
        self._update_range(gain=16, integration_time=13)
        self.last_vnir = None
        self.last_ir = None

    def _register8(self, register, value=None):
        # Read or write a byte to the device
        register |= _COMMAND_BIT
        if value is None:
            return self._device.readU8(register)
        return self._device.write8(register, value)  

    def _register16(self, register, value=None):
        # Read or write a word to the device
        register |= _COMMAND_BIT | _WORD_BIT
        if value is None:
            return self._device.readU16(register)
        return self._device.writeU16(register, value)      

    def _lux(self, channels):
        if self._integration_time == 0:
            raise ValueError(
                "can't calculate lux with manual integration time")
        vnir, ir = channels
        clip = _INTEGRATION_TIME[self._integration_time][2]
        if vnir > clip or ir > clip:
            self._logger.warning('The device is saturated (gain={0} integration_time={1} vnir={2} ir={3}'.format(self._gain, self._integration_time, vnir, ir))
            return None
        #scale = _INTEGRATION_TIME[self._integration_time][5] / self._gain
        scale = 16 * _INTEGRATION_TIME[self._integration_time][5] / self._gain
        channel0 = (vnir * scale) / 1024
        channel1 = (ir * scale) / 1024
        ratio = (((channel1 * 1024) / channel0 if channel0 else 0) + 1) / 2
        for k, b, m in self._LUX_SCALE:
            if ratio <= k:
                break
        else:
            b = 0
            m = 0
        return (max(0, channel0 * b - channel1 * m) + 8192) / 16384

    def _read(self):
        # read with power management
        if self._gain is None or self._integration_time is None:
            raise ValueError(
                "Set the gain and integration time before attempting to read")
        was_active = self.active()
        if not was_active:
            self.active(True)
            # if the sensor was off, wait for measurement
            time.sleep(_INTEGRATION_TIME[self._integration_time][1] / 1000)
        vnir = self._register16(_REGISTER_CHANNEL0)
        ir = self._register16(_REGISTER_CHANNEL1)
        self.active(was_active)
        return vnir, ir

    def sensor_id(self):
        # Return the part and revision number of the device
        ''' 
        Part numbers from TSL2560-61_DS000110_2-00.pdf
        0000 TSL2560CS
        0001 TSL2561CS
        0100 TSL2560T/FN/CL
        0101 TSL2561T/FN/CL <- Adafruit PRODUCT ID: 439
        '''
        data = self._register8(_REGISTER_ID)
        return data >> 4, data & 0x0f

    def active(self, value=None):
        # Get or set the power powermode
        if value is None:
            return self._active
        value = bool(value)
        if value != self._active:
            self._active = value
            self._logger.info('Device was {0}'.format('enabled' if value else 'disabled'))
            self._register8(_REGISTER_CONTROL,
                _CONTROL_POWERON if value else _CONTROL_POWEROFF)

    def gain(self, value=None):
        # Get or set the gain
        if value is None:
            return self._gain
        if value not in (1, 16):
            raise ValueError("gain must be either 1x or 16x")
        self._update_range(gain=value)

    def integration_time(self, value=None):
        # Get or set the integration time
        if value is None:
            return self._integration_time
        if value not in _INTEGRATION_TIME:
            raise ValueError("integration time must be 0, 13ms, 101ms or 402ms")
        self._update_range(integration_time=value)

    def _update_range(self, gain=None, integration_time=None):
        # Set the gain and/or integration time
        # Reference:
        #   TSL258x: Accurate ADC Readings after Enable
        #   http://ams.com/eng/content/view/download/174915        
        was_active = self.active()
        if gain is not None and gain != self._gain:
            # Power down before changing the gain
            if was_active:
                self.active(False)
            value = self._register8(_REGISTER_TIMING) & 0x03
            self._register8(_REGISTER_TIMING, value | {1: 0x00, 16: 0x10}[gain])
            self._gain = gain
            self._logger.info('Gain was set to {0}x (0x{1:x})'.format(gain, self._register8(_REGISTER_TIMING)))
        if integration_time is not None and integration_time != self._integration_time:
            value = self._register8(_REGISTER_TIMING) & 0x10
            self._register8(_REGISTER_TIMING, value | _INTEGRATION_TIME[integration_time][0])
            self._logger.info('Integration time was set to {0}ms (0x{1:x})'.format(integration_time, self._register8(_REGISTER_TIMING)))
            # Wait at least one integration cycle after changing integration_time
            time.sleep(max(_INTEGRATION_TIME[self._integration_time][1], _INTEGRATION_TIME[integration_time][1]) / 1000)            
            self._integration_time = integration_time
        self.active(was_active)        

    def read(self, autogain=False, hdr=False, raw=False):
        if hdr:
            while True:
                vnir, ir = self._read()
                if self._hdr is None:
                    self._logger.info('HDR was enabled')
                    self._hdr = 0
                elif (vnir == 0 and ir == 0 and self._hdr != 0):
                    self._logger.warning('HDR waiting for device to thaw')
                    time.sleep(1)
                elif (_HDR[self._hdr]['max'] is not None and max(vnir, ir) > _HDR[self._hdr]['max']):
                    self._logger.info('HDR thinks this porridge is too hot (_hdr={0} vnir={1} ir={2})'.format(self._hdr, vnir, ir))
                    self._hdr += 1
                elif (_HDR[self._hdr]['min'] is not None and vnir < _HDR[self._hdr]['min']):
                    self._logger.info('HDR thinks this porridge is too cold right (_hdr={0} vnir={1} ir={2})'.format(self._hdr, vnir, ir))
                    self._hdr -= 1
                else:
                    self._logger.info('HDR thinks this porridge is just right (_hdr={0} vnir={1} ir={2})'.format(self._hdr, vnir, ir))
                    break
                self._update_range(gain=_HDR[self._hdr]['gain'], integration_time=_HDR[self._hdr]['time'])
                #self.gain(_HDR[self._hdr]['gain'])
                #self.integration_time(_HDR[self._hdr]['time'])
            self.last_vnir, self.last_ir = vnir, ir
            return self._lux((vnir, ir))

        else:
            self._logger.info('HDR was disabled')
            self._hdr = None
            vnir, ir = self._read()
            if autogain:
                if self._integration_time == 0:
                    raise ValueError(
                        "can't do autogain with manual integration time")
                new_gain = self._gain
                if vnir < _INTEGRATION_TIME[self._integration_time][3]:
                    new_gain = 16
                elif vnir > _INTEGRATION_TIME[self._integration_time][4]:
                    new_gain = 1
                if new_gain != self._gain:
                    self.gain(new_gain)
                    vnir, ir = self._read()
                self._logger.info('autogain ({0}x {1}ms {2}/{3})'.format(self._gain, self._integration_time, vnir, ir))
            if raw:
                return vnir, ir
            return self._lux((vnir, ir))

    def threshold(self, cycles=None, min_value=None, max_value=None):
        if min_value is None and max_value is None and cycles is None:
            min_value = self._register16(_REGISTER_THRESHHOLD_MIN)
            max_value = self._register16(_REGISTER_THRESHHOLD_MAX)
            cycles = self._register8(_REGISTER_INTERRUPT)
            if not cycles & _INTERRUPT_LEVEL:
                cycles = -1
            else:
                cycles &= 0x0f
            return cycles, min_value, max_value
        was_active = self.active()
        self.active(True)
        if min_value is not None:
            self._register16(_REGISTER_THRESHHOLD_MIN, int(min_value))
        if max_value is not None:
            self._register16(_REGISTER_THRESHHOLD_MAX, int(max_value))
        if cycles is not None:
            if cycles == -1:
                self._register8(_REGISTER_INTERRUPT, _INTERRUPT_NONE)
            else:
                self._register8(_REGISTER_INTERRUPT,
                    min(15, max(0, int(cycles))) | _INTERRUPT_LEVEL)
        self.active(was_active)

    def interrupt(self, value):
        if value or value is None:
            raise ValueError("can only clear the interrupt")
        self.i2c.writeto_mem(self.address,
            _CLEAR_BIT | _REGISTER_CONTROL, b'\x00')

TSL2561T  = TSL2561
TSL2561FN = TSL2561
TSL2561CL = TSL2561

class TSL2561CS(TSL2561):
    # This package has different lux scale.
    _LUX_SCALE = (
    #       K       B       M
        (0x0043, 0x0204, 0x01ad),
        (0x0085, 0x0228, 0x02c1),
        (0x00c8, 0x0253, 0x0363),
        (0x010a, 0x0282, 0x03df),
        (0x014d, 0x0177, 0x01dd),
        (0x019a, 0x0101, 0x0127),
        (0x029a, 0x0037, 0x002b),
    )
        
if __name__ == "__main__":
    tsl = TSL2561(address=TSL2561_ADDR_HIGH, powermode=TSL2561_LOWPOWER, debug=True)
    print tsl.read(hdr=True)
