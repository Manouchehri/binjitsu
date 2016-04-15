import os
import re
import tempfile

from . import atexit
from . import tubes
from .context import context
from .log import getLogger
from .util import misc

log = getLogger(__name__)

def adb(argv, *a, **kw):
    if isinstance(argv, (str, unicode)):
        argv = [argv]

    serial = kw.pop('serial', None)

    if serial:
        argv = ['-s', serial] + argv

    return tubes.process.process(context.adb + argv).recvall()

def root():
    serial = get_serialno()
    
    with context.local(log_level='error'):
        reply  = adb('root')

    if 'restarting adbd as root' not in reply \
    and 'adbd is already running as root' not in reply:
        log.error("Could not run as root:\n%s" % reply)

    wait_for_device(serial)

def reboot(wait=True):
    serial = get_serialno()
    
    with context.local(log_level='error'):
        adb('reboot')

    if wait: wait_for_device(serial)

def reboot_bootloader():
    with context.local(log_level='error'):
        adb('reboot-bootloader')

def get_serialno():
    with context.local(log_level='error'):
        reply = adb('get-serialno')

    if 'unknown' in reply:
        log.error("No devices connected")
    return reply.strip()

def wait_for_device(serial=None):
    msg = "Waiting for device %s to come online" % (serial or '(any)')
    with log.waitfor(msg) as w:
        with context.local(log_level='error'):
            adb('wait-for-device', serial=serial)

        if not serial:
            serial = get_serialno()
            w.success(serial)
    return serial

def foreach(callable=None):
    with context.local(log_level='error'):
        reply = adb('devices')

    for line in reply.splitlines():
        if 'List of devices' in line:
            continue
        
        if not line:
            continue

        serial = line.split()[0]

        if callable is None:
            yield serial
            continue

        original = os.environ.get('ANDROID_SERIAL', None)
        try:
            os.environ['ANDROID_SERIAL'] = serial
            callable()
        finally:
            if original is not None:
                os.environ['ANDROID_SERIAL'] = original
            else:
                del os.environ['ANDROID_SERIAL']

def disable_verity():
    root()

    with context.local(log_level='error'):
        reply = adb('disable-verity')

    if 'Verity already disabled' in reply:
        return
    elif 'Now reboot your device' in reply:
        reboot(wait=True)
    else:
        log.error("Could not disable verity:\n%s" % reply)


def remount():
    with context.local(log_level='error'):
        reply = adb('remount')

    if 'remount succeeded' not in reply:
        log.error("Could not remount filesystem:\n%s" % reply)

def unroot():
    with context.local(log_level='error'):
        reply  = adb('unroot')

    if 'restarting adbd as non root' not in reply:
        log.error("Could not run as root:\n%s" % reply)


def read(path, target=None):
    with tempfile.TemporaryFile() as temp:
        target = target or temp.name
        reply  = adb(['pull', path, target])

        if ' bytes in ' not in reply:
            log.error("Could not read %r:\n%s" % (path, reply))

        result = misc.read(target)
    return result

def write(path, data=''):
    with tempfile.TemporaryFile() as temp:
        misc.write(temp.name, data)

        reply  = adb(['push', temp.name, path])

        if ' bytes in ' not in reply:
            log.error("Could not read %r:\n%s" % (path, reply))

def process(argv, *a, **kw):
    argv = argv or []
    if isinstance(argv, (str, unicode)):
        argv = [argv]
    argv = context.adb + ['shell'] + argv
    return tubes.process.process(argv, *a, **kw)

def shell():
    return process([])

def which(name):
    with context.local(log_level='error'):
        return process(['which', name]).recvall().strip()

def forward(port):
    tcp_port = 'tcp:%s' % port
    start_forwarding = adb(['forward', tcp_port, tcp_port])
    atexit.register(lambda: adb(['forward', '--remove', tcp_port]))

def logcat(extra='-d'):
    return adb(['logcat', extra])

def pidof(name):
    with context.local(log_level='error'):
        io = process(['pidof', name])
        data = io.recvall().split()
    return list(map(int, data))

def proc_exe(pid):
    with context.local(log_level='error'):
        io  = process(['readlink','-e','/proc/%d/exe' % pid])
        data = io.recvall().strip()
    return data

def getprop(name=None):
    with context.local(log_level='error'):
        if name:
            return process(['getprop', name]).recvall().strip()


        result = process(['getprop']).recvall()

    expr = r'\[([^\]]+)\]: \[(.*)\]'

    props = {}

    for line in result.splitlines():
        if not line.startswith('['):
            continue

        name, value = re.search(expr, line).groups()

        if value.isdigit():
            value = int(value)

        props[name] = value

    return props

def fingerprint():
    return getprop('ro.build.fingerprint')

def product():
    return getprop('ro.build.product')

def build():
    return getprop('ro.build.id')