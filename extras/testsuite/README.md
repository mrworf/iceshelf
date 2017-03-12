# testsuite

A beginning to a suite of tests to confirm that the tool is doing the right thing.

All the test cases are places inside `tests/` folder and essentially manipulate the
content folder and then execute the `runTest` call.

runTest take the following arguments:

- param1 = title of test
- param2 = leave empty to run `iceshelf` with `--changes`. If no changes are detected, the test fails
- param3 = provide `pretest()` and `posttest()` functions which are called before or after test, return non-zero to fail test
- param4 = Which config file to use (unrelated to variant)
-- regular = Simple backup
-- prefix = Sets the prefix option
-- filelist = produces a *.lst file
-- encryptmani = Also encrypts manifest
-- *NOTE* These configurations are also adapted based on variant, so variant encrypted will make all configs produce encrypted output
- param5 = Text to compare output from `diff` of the source material and the resulting unpacked backup. If prefixed with `^` it will assume the text is a regular expression, otherwise it's just plain text comparison.
- param6+ passed verbaitum to iceshelf

_Of all these options, only 5 & 6 can be left empty._

By setting the `ERROR` environment variable to `true`, you will trigger an error. This
is done automatically inside `runTest` so unless you have specific needs, you shouldn't
have to do anything.

There are a number of other variables acccessible:

- VARIANT indicates the current variant the test is used in, some cases (like #012) depend on this

All tests are run in numerical order and therefore can depend on the output from the
previous testcase.

All tests are run multiple times in various configurations (encryption, signature, etc).