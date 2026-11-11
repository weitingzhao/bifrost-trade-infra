"""Keep the reuse Task's isolated Python identical to its tested source."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'k8s/cicd/tekton/task-ci-platform-reuse.yaml'
text = path.read_text().split('      script: |\n')[0]
source = (ROOT / 'scripts/release/platform_ci_reuse.py').read_text()
path.write_text(text + '      script: |\n        #!/usr/bin/env python3\n' + ''.join('        ' + line + '\n' if line else '\n' for line in source.splitlines()))
