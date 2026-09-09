"""Pinned Kotlin PSI expression parser. Does not load or execute application classes."""
import atexit
import functools
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import threading


class KotlinPsiError(ValueError):
    pass


class KotlinPsiSyntaxError(KotlinPsiError):
    pass


ARTIFACTS = (
    ('org.jetbrains.kotlin', 'kotlin-compiler-embeddable', '1.9.22'),
    ('org.jetbrains.kotlin', 'kotlin-stdlib', '1.9.22'),
    ('org.jetbrains.kotlin', 'kotlin-reflect', '1.6.10'),
    ('org.jetbrains.intellij.deps', 'trove4j', '1.0.20200330'),
    ('org.jetbrains', 'annotations', '13.0'),
    ('com.google.code.gson', 'gson', '2.10.1'),
)
_process = None
_lock = threading.Lock()


def close():
    global _process
    if _process is not None:
        _process.stdin.close()
        try:
            _process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _process.kill()
            _process.wait()
        _process.stdout.close()
        _process = None


atexit.register(close)


def start():
    jars = []
    cache = Path(os.environ.get('GRADLE_USER_HOME', str(Path.home() / '.gradle'))) / 'caches/modules-2/files-2.1'
    configured = os.environ.get('KOTLIN_PSI_CLASSPATH')
    if configured:
        jars = [Path(p) for p in configured.split(os.pathsep)]
    else:
        for group, artifact, version in ARTIFACTS:
            matches = list((cache / group / artifact / version).glob(f'*/{artifact}-{version}.jar'))
            if len(matches) != 1:
                raise KotlinPsiError(f'Kotlin PSI dependency missing: {group}:{artifact}:{version}; set KOTLIN_PSI_CLASSPATH')
            jars.append(matches[0])
    if not jars or any(not p.is_file() for p in jars):
        raise KotlinPsiError('KOTLIN_PSI_CLASSPATH must contain readable compiler and runtime JARs')
    source = Path(__file__).with_name('kotlin_psi') / 'KotlinExpressionTree.java'
    digest = hashlib.sha256(b'java-release-17\n' + source.read_bytes() + '\n'.join(str(p) for p in jars).encode()).hexdigest()
    output = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'android-to-harmony/kotlin-psi' / digest
    output.mkdir(parents=True, exist_ok=True)
    java_home = os.environ.get('JAVA_HOME')
    def executable(name):
        return str(Path(java_home) / 'bin' / name) if java_home else shutil.which(name)
    classpath = os.pathsep.join(map(str, jars))
    if not (output / 'KotlinExpressionTree.class').exists():
        result = subprocess.run([executable('javac'), '--release', '17', '-encoding', 'UTF-8', '-cp', classpath,
                                 '-d', str(output), str(source)], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise KotlinPsiError('Kotlin PSI bridge compilation failed: ' + result.stderr[-4000:])
    return subprocess.Popen([executable('java'), '-Xmx256m', '-cp', str(output) + os.pathsep + classpath,
                             'KotlinExpressionTree'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True, encoding='utf-8', bufsize=1)


@functools.lru_cache(maxsize=4096)
def parse_expression(expression):
    if not isinstance(expression, str) or len(expression) > 65536:
        raise KotlinPsiError('expected a Kotlin expression of at most 64 KiB')
    return _request(expression)


@functools.lru_cache(maxsize=128)
def parse_declarations(source):
    if not isinstance(source, str) or len(source) > 1048576:
        raise KotlinPsiError('expected a Kotlin source file of at most 1 MiB')
    return _request({'source': source})


def _request(request):
    global _process
    with _lock:
        if _process is None or _process.poll() is not None:
            _process = start()
        _process.stdin.write(json.dumps(request) + '\n')
        _process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(_process.stdout, selectors.EVENT_READ)
            if not selector.select(timeout=20):
                close()
                raise KotlinPsiError('Kotlin PSI expression parsing timed out')
        line = _process.stdout.readline()
        if not line:
            close()
            raise KotlinPsiError('Kotlin PSI process exited before returning a syntax tree')
        result = json.loads(line)
        if result.get('kind') == 'error':
            raise KotlinPsiSyntaxError(result['message'])
        return result
