import re
import sys


def main(orig_bp, changed_bp, old_version, new_version):
    with open(orig_bp, 'r') as orig_bp_f:
        with open(changed_bp, 'w') as changed_bp_f:
            esc_old_3v = re.escape(old_version)
            esc_old_1v = '1' + esc_old_3v[1:] # 1.x.x versioned modules
            new_1x_version = '1' + new_version[1:]
            def substitute_version(matchobj):
                version = matchobj.group(1)
                remainder = matchobj.group(2)
                if version.startswith('3'):
                    nv = new_version
                else:
                    nv = new_1x_version
                return nv + remainder
            modified_content = re.sub(
                '(' + esc_old_3v + '|'+ esc_old_1v + ')(.*(yaml|yml|zip))',
                substitute_version,
                orig_bp_f.read()
            )
            changed_bp_f.write(modified_content)


if __name__ == '__main__':
    main(*sys.argv[1:])
