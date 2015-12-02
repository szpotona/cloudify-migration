import json
import yaml
import sys

from dsl_parser.parser import parse_from_path
from dsl_parser.exceptions import DSLParsingException


def _json_dump(path, content):
    with open(path, 'w') as f:
        f.write(json.dumps(content, indent=2))


def main(args):
    blueprint_path = args[1]
    result_path = args[2]
    result = {}
    try:
        blueprint = parse_from_path(blueprint_path)
        if 'nodes' not in blueprint:
            result['ok'] = False
        else:
            result['ok'] = True
            result['nodes'] = [n['name'] for n in blueprint['nodes']]
    except (DSLParsingException, yaml.scanner.ScannerError):
        result['ok'] = False
    _json_dump(result_path, result)


if __name__ == '__main__':
    main(sys.argv)
