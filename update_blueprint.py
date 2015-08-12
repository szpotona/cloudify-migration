import re
import sys


def main(orig_bp, changed_bp, old_version, new_version):
    with open(orig_bp, 'r') as orig_bp_f:
        with open(changed_bp, 'w') as changed_bp_f:
            esc_old_3v = re.escape(old_version)
            esc_old_1v = '1' + esc_old_3v[1:] # 1.x.x versioned modules
            new_1x_version = '1' + new_version[1:]

            def substitute_ver(mo):
                version = mo.group(0)
                if version.startswith('3'):
                    return new_version
                else:
                    return new_1x_version

            def substitute_versions(matchobj):
                link = matchobj.group(0)
                return re.sub('(' + esc_old_3v + '|'+ esc_old_1v + ')', substitute_ver, link)

            modified_content = re.sub(
                'http.*(yaml|yml|zip)',
                substitute_versions,
                orig_bp_f.read()
            )
            changed_bp_f.write(modified_content)


if __name__ == '__main__':
    main(*sys.argv[1:])
