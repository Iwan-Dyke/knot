"""Audited offline assets and redistribution notices shared by both viewers."""

from hashlib import sha256
from importlib import metadata
from pathlib import Path

ASSETS = Path(__file__).parent
VIS_SCRIPT = 'lib/vis-9.1.2/vis-network.min.js'
VIS_STYLE = 'lib/vis-9.1.2/vis-network.css'
# Hash UTF-8 text after newline normalisation, matching both rendering paths.
# Update the audit and complete notices before accepting different asset bytes.
AUDITED = {
    VIS_SCRIPT: 'f3c1229464749a6f5a80c80867189edfdc0198be0d015c3d770aff196cb6c0a1',
    VIS_STYLE: '2e82d445ad5878ea881652470ce632601f8f55f1b99e6ebecdff8614600e6d0e',
    'template.html': 'cc42e96b51f546f0057f680b1ddc77a0d09ee33a89144b188c16af5bb16bc348',
    'lib/bindings/utils.js': '3113c73317c30c99eaafbc782916160ce7d23183a148615da0496643e9560cb0',
}


def load_viewer_assets(*, legacy=False):
    try:
        import pyvis
    except ImportError as error:
        raise ValueError(
            'Install KNOT with the visualisation extra to export the interface'
        ) from error
    if metadata.version('pyvis') != '0.3.2':
        raise ValueError('Viewer licence audit needs review for this PyVis version')
    root = Path(pyvis.__file__).parent / 'templates'
    selected = AUDITED if legacy else (VIS_SCRIPT, VIS_STYLE)
    loaded = {}
    for name in selected:
        text = (root / name).read_text(encoding='utf-8')
        if sha256(text.encode('utf-8')).hexdigest() != AUDITED[name]:
            raise ValueError('Viewer licence audit needs review for changed assets: ' + name)
        loaded[name] = text
    return loaded


def software_notices(*, legacy=False):
    names = ['knot-license.txt', 'vis-network-license.txt', 'vis-network-dependencies-license.txt']
    if legacy:
        names.append('pyvis-license.txt')
    return 'KNOT application and bundled software (not your knowledge content)\n\n' + '\n\n'.join(
        (ASSETS / name).read_text(encoding='utf-8') for name in names
    )
