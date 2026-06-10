#!/usr/bin/env fish

set -l root (cd (dirname (status filename)); and pwd)
cd $root

if not command -q npm
    echo "npm is required to build the extension." >&2
    exit 1
end

if test -f package-lock.json
    npm ci
else
    npm install
end
or exit $status

npm run test
or exit $status

npm run prepare:pyright
or exit $status

rm -f "$root/xonsh-language-support.vsix"
npx vsce package --allow-missing-repository --out "$root/xonsh-language-support.vsix"
or exit $status

echo "Built $root/xonsh-language-support.vsix"
