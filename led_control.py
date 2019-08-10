#!/usr/bin/env python3
import logging
import time
import requests
import os
import yaml


def int_to_hex(_int):
    """Cast int to correctly formatted hex number for RGB colour strings"""
    if _int > 255:
        return "ff"
    elif _int < 0:
        return "00"
    else:
        return "{:0>2}".format(hex(_int)[2:])


def rgb_to_str(_list):
    """convert and [r,g,b] int list to a hex string"""
    return "".join([int_to_hex(int(x)) for x in _list])


class Monitor:
    def __init__(self, locations, default=None):
        self.locations = set()
        if type(locations) == str:
            locations = [locations]
        for location in locations:
            if location not in ["left", "right", "center", "extra"]:
                raise AttributeError("{} is not a valid location".format(location))
            self.locations.add(location)
        if default is None:
            self.current_colour = rgb_to_str([0, 0, 255])
        else:
            self.current_colour = default

        self._update_leds()
        self._update_brighness(100)

    def _update_brighness(self, brightness: int = 100):
        with open("/sys/class/leds/system76::kbd_backlight/brightness", "w") as fh:
            fh.write(str(max(100, min(0, int(brightness)))))

    def _update_leds(self):
        fn_prefix = "/sys/class/leds/system76::kbd_backlight/color_"
        for location in self.locations:
            with open(fn_prefix + location, "w") as fh:
                fh.write(self.current_colour)

    def update(self):
        pass


class site_health(Monitor):

    status_colours = {
        "unknown": rgb_to_str([0, 0, 255]),
        "good": rgb_to_str([0, 255, 0]),
        "degraded": rgb_to_str([192, 192, 0]),
        "bad": rgb_to_str([255, 0, 0]),
    }
    last_update = 0

    def __init__(self, locations, url, headers=None, timeout=5, frequency=10):
        self.url = url
        self.timeout = timeout
        self.frequency = frequency
        if headers is None:
            self.headers = {}
        else:
            self.headers = headers
        super().__init__(locations, self.status_colours["unknown"])

        logging.info("site_health monitor setup for %s", ", ".join(self.locations))

    def update(self):
        if time.time() - self.last_update < self.frequency:
            return
        start = time.time()
        try:
            r = requests.get(self.url, headers=self.headers, timeout=self.timeout)
        except Exception:
            logging.exception('Failed to get status of %s', self.url)
            self.current_colour = self.status_colours["unknown"]
        else:
            if r.status_code == 200 and time.time() - start < 1:
                self.current_colour = self.status_colours["good"]
            elif r.status_code == 200:
                self.current_colour = self.status_colours["degraded"]
            else:
                self.current_colour = self.status_colours["bad"]

        self._update_leds()
        self.last_update = time.time()


class load_average(Monitor):
    """
    A monitor to simply set the LED colour to match the 1m load avg on a red to green scale.
    """

    def __init__(self, locations, default=None):
        super().__init__(locations, default)
        logging.info("load_average monitor setup for %s", ", ".join(self.locations))

    def update(self):
        cpu_cores = 8
        load_avg = min(255 * os.getloadavg()[0] / cpu_cores, 255)
        self.current_colour = rgb_to_str([load_avg, 255 - load_avg, 0])
        self._update_leds()


class pulse(Monitor):
    def __init__(self, locations, default=None, a_colour=None, b_colour=None, speed=5):
        super().__init__(locations, default)
        if a_colour is None:
            self.a_colour = [0,0,255]
        else:
            self.a_colour = a_colour
        if b_colour is None:
            self.b_colour = [255,0,0]
        else:
            self.b_colour = b_colour
        self.position = 0
        self.speed = speed
        logging.info("pulse setup for %s", ", ".join(self.locations))

    def update(self):
        p = self.position
        a = self.a_colour
        b = self.b_colour
        colour = [a[x]*(100-p)/100+b[x]*p/100 for x in range(3)]

        self.current_colour = rgb_to_str(colour)
        self._update_leds()
        self.position += self.speed
        if self.position > 100:
            self.position = 0
        logging.info(self.current_colour)



def main():

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    logging.info("loading config")
    with open("/etc/led_control.yaml", "r") as fh:
        config = yaml.safe_load(fh.read())

    available_monitors = {"site_health": site_health, "load_average": load_average, "pulse":pulse}

    monitors = []

    for name, config in config["monitors"].items():
        monitor = available_monitors[name](**config)
        monitors.append(monitor)

    while True:
        for monitor in monitors:
            monitor.update()
        time.sleep(0.1)


if __name__ == "__main__":
    main()
