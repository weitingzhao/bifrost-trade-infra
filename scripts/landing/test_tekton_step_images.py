"""No Tekton step pulls its image from the registry's cluster Service name (TD-467).

A node pulls a step image with containerd, outside cluster DNS: an image at
registry.cicd.svc.cluster.local:5000 ends in ErrImagePull (ci-infra run
bifrost-ci-infra-1793424335, 2026-10-31). Every platform image is pinned at
the registry NodePort instead, and step images use that host too. Kaniko's
--destination is a push from inside the pod, under args, not an image, and is
not covered.

Covered: every ``image`` of a ``steps``, ``sidecars``, ``containers`` or
``initContainers`` entry in any document under k8s/cicd/tekton, at any depth
(Task steps, Pipeline and PipelineRun inline taskSpecs, TriggerTemplate
resource templates, CronJob pod templates).
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / 'k8s/cicd/tekton'
CLUSTER_SERVICE_HOST = re.compile(r'^[^/@]*\.svc(\.cluster\.local)?(:\d+)?/')
IMAGE_LISTS = ('steps', 'sidecars', 'containers', 'initContainers')


def images(node, where=''):
    """Every (location, image) under a parsed YAML document."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in IMAGE_LISTS and isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict) and 'image' in entry:
                        found.append((where + '/' + key + '/' + str(entry.get('name', '?')), entry['image']))
            found.extend(images(value, where + '/' + str(key)))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(images(value, where + '/' + str(i)))
    return found


def document_images(tekton=TEKTON):
    """(file, location, image) for every manifest under the Tekton directory."""
    found = []
    for path in sorted(tekton.glob('*.yaml')):
        for i, doc in enumerate(yaml.safe_load_all(path.read_text())):
            if not isinstance(doc, dict):
                continue
            label = f"{doc.get('kind', '?')}/{(doc.get('metadata') or {}).get('name', i)}"
            found.extend((path.name, label + where, image) for where, image in images(doc))
    return found


def violations(tekton=TEKTON):
    return [f'{name}: {where}: {image}' for name, where, image in document_images(tekton)
            if isinstance(image, str) and CLUSTER_SERVICE_HOST.match(image)]


def test_no_step_image_names_the_registry_cluster_service():
    assert violations() == []


def test_walk_sees_the_s5_and_ci_infra_steps():
    # Positive control: the images the Owner's run and TD-467 are about are in the walk.
    seen = {(name, where) for name, where, _ in document_images()}
    assert ('task-s5-check.yaml', 'Task/bifrost-s5-check/spec/steps/check') in seen
    assert ('task-s5-fetch.yaml', 'Task/bifrost-s5-fetch/spec/steps/fetch') in seen
    assert ('pipeline-build-s5-checker.yaml',
            'Pipeline/bifrost-build-s5-checker/spec/tasks/5/taskSpec/steps/read-materials') in seen
    assert ('task-ci-infra-resolve.yaml', 'Task/bifrost-ci-infra-resolve/spec/steps/resolve') in seen
    assert sum(1 for name, _ in seen if name.startswith('task-')) >= 30


def test_service_name_in_a_task_or_inline_step_is_reported(tmp_path):
    for name in ('task-s5-check.yaml', 'pipeline-build-s5-checker.yaml', 'task-ci-infra-clone.yaml'):
        (tmp_path / name).write_text((TEKTON / name).read_text())
    assert violations(tmp_path) == []
    service = 'registry.cicd.svc.cluster.local:5000/bifrost-s5-checker@'
    task = tmp_path / 'task-s5-check.yaml'
    task.write_text(task.read_text().replace('192.168.10.73:30500/bifrost-s5-checker@', service))
    pipeline = tmp_path / 'pipeline-build-s5-checker.yaml'
    pipeline.write_text(pipeline.read_text().replace('192.168.10.73:30500/bifrost-s5-checker@', 'registry.cicd.svc:5000/bifrost-s5-checker@'))
    found = violations(tmp_path)
    assert [v.split(': ')[0] + ': ' + v.split(': ')[1] for v in found] == [
        'pipeline-build-s5-checker.yaml: Pipeline/bifrost-build-s5-checker/spec/tasks/5/taskSpec/steps/read-materials',
        'task-s5-check.yaml: Task/bifrost-s5-check/spec/steps/check',
    ]
    # Kaniko still pushes through the Service name from inside the pod: an arg, not an image.
    assert 'registry.cicd.svc.cluster.local:5000/bifrost-s5-checker:' in pipeline.read_text()
    assert not any('build-and-push' in v for v in found)


def test_only_a_cluster_service_host_is_a_violation():
    for image in ('192.168.10.73:30500/bifrost-s5-checker@sha256:' + '1' * 64,
                  'gcr.io/kaniko-project/executor:v1.23.2', 'python:3.12-slim-bookworm', 'alpine',
                  'ghcr.io/svc.cluster.local/tool:1'):
        assert not CLUSTER_SERVICE_HOST.match(image), image
    for image in ('registry.cicd.svc.cluster.local:5000/x@sha256:' + '0' * 64,
                  'registry.cicd.svc.cluster.local/x:1', 'registry.cicd.svc:5000/x:1'):
        assert CLUSTER_SERVICE_HOST.match(image), image


if __name__ == '__main__':
    problems = violations()
    print('\n'.join(problems))
    raise SystemExit(1 if problems else 0)
