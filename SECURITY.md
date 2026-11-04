# Security policy

Please do not report security problems in public issues.

Report them privately through [GitHub's private vulnerability reporting](https://github.com/T3-Venture-Labs-Limited/short-stock/security/advisories/new). Include what you found, how to reproduce it, and its impact. We will reply as soon as we can.

shortstock is designed to run locally. The web app has no login and listens on localhost by default; do not expose it to the internet without authentication in front of it. API keys are stored in the local SQLite database in `SHORTSTOCK_HOME`.
