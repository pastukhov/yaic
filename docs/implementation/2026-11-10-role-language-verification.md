# Role response language correction

YAIC_LANGUAGE already reached RoleClassifier, but its prompt required English
machine role codes and Processor exposed that code as display text. RoleClassifier
now requests role_name and reason in the configured language; Russian default
roles also have canonical Russian labels. RoleResult.role remains the code;
Processor emits display person.role and stable person.role_code. Telegram gateway
translation was not introduced.

Regression tests were observed failing before the change, then passing. Complete
suite:113 passed in persistent local dependency environment and in production
Python3.11 image using existing cached pure-Python test dependencies. Review found
no blocking localization errors; role/role_code contract documented in README.

Live face-calibration evidence and deployment overrides are recorded only in
private operational notes. No screenshots, face vectors, personal identities or
private deployment parameters are included here.
