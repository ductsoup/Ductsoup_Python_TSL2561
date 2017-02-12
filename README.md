# Ductsoup_Python_TSL2561
A more complete Raspberry Pi library for TSL2561 based on [micropython-adafruit-tsl2561](https://github.com/adafruit/micropython-adafruit-tsl2561).

In addition to the raw and autogain options of the original, this library includes a high dynamic range option to automatically utilize the full potential of the device. The other significant difference is the application of the guidance from DN42 to improve stability when changing gain or integration time in either normal or low power mode.

## Requirements

This driver requires that you have previously installed the
[Adafruit_Python_GPIO](https://github.com/adafruit/Adafruit_Python_GPIO) package.

You can install this package with the following commands:

```
$sudo apt-get update
$sudo apt-get install build-essential python-pip python-dev python-smbus git i2c-tools
$git clone https://github.com/adafruit/Adafruit_Python_GPIO.git
$cd Adafruit_Python_GPIO
$sudo python setup.py install
$cd ~
```

## Installation
```
$git clone https://github.com/ductsoup/Ductsoup_Python_TSL2561.git
$cd Ductsoup_Python_TSL2561
$sudo python setup.py install
```
## Usage
```
from Ductsoup_Python_TSL2561 import *
tsl = TSL2561()
print tsl.read(hdr=True)
```

In full daylight the sensor will likely saturate. Whenever the light is above or below the limits of the device, the returned value will be None. Otherwise the returned value will be in lux.

## Other Similar Breakouts
While designed for the [Adafruit breakout](https://www.adafruit.com/product/439) it should be possible to adapt the code to other packages in the same family by adjusting these lines in the ```__init__``` section of the class.

```
# Verify device ID
self.part_no, self.rev_no = self.sensor_id()
if not self.part_no & 0x01:
    raise RuntimeError("bad sensor id 0x{:x}".format(self.part_no << 4 | self.rev_no))
 else:
    self._logger.info('Device found (partno={0}, revision={1})'.format(self.part_no, self.rev_no))
```

## Credit
Thanks to Radomir Dopieralski for providing a fine place to start.

## MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

