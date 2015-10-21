# TODO

This file details what my goals are for this project, both in the short term and in the long term. It also details items which I intend to do but doesn't have a clear time plan. 

The list is intentionally kept vague to avoid over-promising and under-delivering :)

## Short term
- Add support for embedding manifest inside backup instead of separately
- Add support for encrypting manifest outside backup instead of plain text
- Add support for restoring backups

## Long term
- Detect duplication when using sha method (impossible with meta due to lack of details)

## Anytime
- Cleanup parameters
- Add info about http://www.jabberwocky.com/software/paperkey/ to README.md
- improve --modified output (min, max, etc)
- add warning if one and the same file changes a lot
- Add piece about "why encrypt" to README.md (ie, why I am so adamant about it). See second section in this file for current links about security until I get around to putting it in the README.md

# Why use iceshelf with encryption?

- http://arstechnica.com/tech-policy/2015/10/microsoft-wants-us-government-to-obey-eu-privacy-laws/
- http://arstechnica.com/tech-policy/2015/10/apple-ceo-tim-cook-blasts-encryption-backdoors/
- http://arstechnica.com/tech-policy/2015/10/judge-does-us-law-allow-feds-to-compel-apple-to-unlock-an-iphone/

