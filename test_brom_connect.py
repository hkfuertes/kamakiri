#!/usr/bin/env python3
"""Exercise the boot0 updater CLI with simulated ports; never access USB/eMMC."""
import importlib
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'modules'))
from common import Device


def check_case(name, modes, crash=False, handshake_error=False):
    module = importlib.import_module(name)
    events, ports = [], []
    remaining = list(modes)

    class Port:
        closed = False
        def close(self):
            assert not self.closed, 'Port closed twice'
            self.closed = True
            events.append('close')

    class FakeDevice(Device):
        def find_device(self):
            assert self.dev is None, 'Previous port was not released'
            assert remaining, 'Mode latch was not reset before reconnecting'
            self.mode = remaining.pop(0)
            # Match real find_device: a BROM PID does not clear a latched True.
            if self.mode == 'preloader':
                self.preloader = True
            self.dev = Port()
            ports.append(self.dev)
            events.append('find:' + self.mode)

        def handshake(self):
            events.append('handshake')
            if handshake_error:
                raise RuntimeError('simulated handshake failure')

        def crash_pl(self):
            events.append('crash')

        def emmc_read(self, *args):
            raise AssertionError('Connection logic accessed eMMC')
        emmc_write = emmc_switch = rpmb_read = rpmb_write = emmc_read

    dev = FakeDevice()
    def load(current):
        assert current is dev and current.mode == 'brom' and not current.preloader
        events.append('load')
    def flash(current, *args):
        assert current is dev and current.mode == 'brom' and not current.preloader
        events.append('flash')

    flash_name = 'flash_boot0'
    overrides = {'Device': lambda: dev, 'check_modemmanager': lambda: None,
                 'load_payload': load, flash_name: flash}
    originals = {key: getattr(module, key) for key in overrides}
    argv, cwd, sleep = sys.argv, Path.cwd(), module.time.sleep
    rejected = False
    try:
        for key, value in overrides.items():
            setattr(module, key, value)
        module.time.sleep = lambda seconds: None
        sys.argv = [name + '.py'] + (['--crash'] if crash else [])
        try:
            module.main()
        except RuntimeError as error:
            assert handshake_error or (modes[0] == 'preloader' and not crash), str(error)
            assert 'preloader' in str(error) or 'handshake failure' in str(error)
            rejected = True
        except SystemExit as error:
            raise AssertionError(name + ': updater CLI does not accept --crash') from error
    finally:
        for key, value in originals.items():
            setattr(module, key, value)
        module.time.sleep = sleep
        sys.argv = argv
        os.chdir(cwd)
    assert all(port.closed for port in ports), 'Serial port leaked'
    if modes[0] == 'preloader' and not crash:
        assert rejected and events == ['find:preloader', 'close']
    elif handshake_error:
        assert rejected and events == ['find:preloader', 'handshake', 'close']
    else:
        expected = []
        for mode in modes:
            expected.append('find:' + mode)
            if mode == 'preloader':
                expected += ['handshake', 'crash', 'close']
        assert not remaining and not rejected
        assert events == expected + ['load', 'flash', 'close'], events


if __name__ == '__main__':
    for name in ('boot0_flash',):
        check_case(name, ['brom'])
        check_case(name, ['preloader'])
        check_case(name, ['preloader', 'brom'], crash=True)
        check_case(name, ['brom'], crash=True)
        check_case(name, ['preloader', 'preloader', 'brom'], crash=True)
        check_case(name, ['preloader'], crash=True, handshake_error=True)
    print('PASS: boot0 updater CLI, default preloader refusal, --crash RAM-only transition/retry, BROM recheck, port cleanup, no storage access (simulation)')
