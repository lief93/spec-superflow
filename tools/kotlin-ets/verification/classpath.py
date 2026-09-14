"""Obtain the exact real Compose compiler input classpath from the Android host."""
import argparse
from pathlib import Path
from common import HERE, Evidence, build_env

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    a = p.parse_args()
    run = a.run.resolve()
    e = Evidence(run / 'classpath')
    raw = e.run('classpath', [run / 'android/gradlew', '-I', HERE / 'compile-classpath.gradle',
                ':app:verificationClasspath', '--offline', '--no-daemon', '--max-workers=2',
                '-Pandroid.useAndroidX=true', '-Dorg.gradle.jvmargs=-Xmx2g'],
                cwd=run / 'android', env=build_env(), timeout=600).decode()
    lines = [line.removeprefix('KOTLIN_ETS_CLASSPATH=') for line in raw.splitlines() if line.startswith('KOTLIN_ETS_CLASSPATH=')]
    assert len(lines) == 1 and all(Path(item).is_file() for item in lines[0].split(':'))
    (run / 'compose-classpath.txt').write_text('\n'.join(lines[0].split(':')) + '\n')
    print(run / 'compose-classpath.txt')
