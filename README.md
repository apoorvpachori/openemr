[![Syntax Status](https://github.com/openemr/openemr/actions/workflows/syntax.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/syntax.yml)
[![Styling Status](https://github.com/openemr/openemr/actions/workflows/styling.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/styling.yml)
[![Testing Status](https://github.com/openemr/openemr/actions/workflows/test.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/test.yml)
[![JS Unit Testing Status](https://github.com/openemr/openemr/actions/workflows/js-test.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/js-test.yml)
[![PHPStan](https://github.com/openemr/openemr/actions/workflows/phpstan.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/phpstan.yml)
[![Rector](https://github.com/openemr/openemr/actions/workflows/rector.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/rector.yml)
[![ShellCheck](https://github.com/openemr/openemr/actions/workflows/shellcheck.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/shellcheck.yml)
[![Docker Compose Linting](https://github.com/openemr/openemr/actions/workflows/docker-compose-lint.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/docker-compose-lint.yml)
[![Dockerfile Linting](https://github.com/openemr/openemr/actions/workflows/hadolint.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/hadolint.yml)
[![Isolated Tests](https://github.com/openemr/openemr/actions/workflows/isolated-tests.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/isolated-tests.yml)
[![Inferno Certification Test](https://github.com/openemr/openemr/actions/workflows/inferno-test.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/inferno-test.yml)
[![Composer Checks](https://github.com/openemr/openemr/actions/workflows/composer.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/composer.yml)
[![Composer Require Checker](https://github.com/openemr/openemr/actions/workflows/composer-require-checker.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/composer-require-checker.yml)
[![API Docs Freshness Checks](https://github.com/openemr/openemr/actions/workflows/api-docs.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/api-docs.yml)
[![codecov](https://codecov.io/gh/openemr/openemr/graph/badge.svg?token=7Eu3U1Ozdq)](https://codecov.io/gh/openemr/openemr)

[![Backers on Open Collective](https://opencollective.com/openemr/backers/badge.svg)](#backers) [![Sponsors on Open Collective](https://opencollective.com/openemr/sponsors/badge.svg)](#sponsors)

# OpenEMR

[OpenEMR](https://open-emr.org) is a Free and Open Source electronic health records and medical practice management application. It features fully integrated electronic health records, practice management, scheduling, electronic billing, internationalization, free support, a vibrant community, and a whole lot more. It runs on Windows, Linux, Mac OS X, and many other platforms.

### Contributing

OpenEMR is a leader in healthcare open source software and comprises a large and diverse community of software developers, medical providers and educators with a very healthy mix of both volunteers and professionals. [Join us and learn how to start contributing today!](https://open-emr.org/wiki/index.php/FAQ#How_do_I_begin_to_volunteer_for_the_OpenEMR_project.3F)

> Already comfortable with git? Check out [CONTRIBUTING.md](CONTRIBUTING.md) for quick setup instructions and requirements for contributing to OpenEMR by resolving a bug or adding an awesome feature 😊.

### Support

Community and Professional support can be found [here](https://open-emr.org/wiki/index.php/OpenEMR_Support_Guide).

Extensive documentation and forums can be found on the [OpenEMR website](https://open-emr.org) that can help you to become more familiar about the project 📖.

### Reporting Issues and Bugs

Report these on the [Issue Tracker](https://github.com/openemr/openemr/issues). If you are unsure if it is an issue/bug, then always feel free to use the [Forum](https://community.open-emr.org/) and [Chat](https://www.open-emr.org/chat/) to discuss about the issue 🪲.

### Reporting Security Vulnerabilities

Check out [SECURITY.md](.github/SECURITY.md)

### API

Check out [API_README.md](API_README.md)

### Docker

Check out [DOCKER_README.md](DOCKER_README.md)

### FHIR

Check out [FHIR_README.md](FHIR_README.md)

### For Developers

If using OpenEMR directly from the code repository, then the following commands will build OpenEMR (Node.js version 24.* is required) :

```shell
composer install --no-dev
npm install
npm run build
composer dump-autoload -o
```

---

## Clinical Co-Pilot — Fork Setup & Deployment

This fork extends OpenEMR with an AI-powered Clinical Co-Pilot. See [NOTES.md](NOTES.md) for architecture decisions and [ARCHITECTURE.md](ARCHITECTURE.md) for the full integration plan.

### Local Development

```bash
# 1. Clone and enter the dev docker environment
git clone https://github.com/YOUR_USERNAME/openemr.git
cd openemr/docker/development-easy

# 2. Start all containers
docker compose up -d

# 3. Build PHP and JS assets (required on first run — not automatic in dev mode)
cd ../..
docker run --rm -v $(pwd):/app -w /app composer:2 install --ignore-platform-reqs --no-interaction
docker compose -f docker/development-easy/docker-compose.yml exec openemr bash -c \
  "cd /var/www/localhost/htdocs/openemr && npm install && node_modules/.bin/gulp -b"

# 4. Load demo patient data
docker compose -f docker/development-easy/docker-compose.yml exec openemr \
  /root/devtools dev-reset-install-demodata

# 5. Generate synthetic patients for testing
docker compose -f docker/development-easy/docker-compose.yml exec openemr \
  /root/devtools import-random-patients 30
```

Access at **http://localhost:8300/** — login: `admin` / `pass`

### Production Deployment (DigitalOcean Droplet)

Deployed using the same development Docker environment on a public server.
See the step-by-step guide below.

**Prerequisites:** A DigitalOcean Droplet running Ubuntu 22.04, 2GB RAM, with your SSH key added.

```bash
# --- On the Droplet (SSH in first) ---

# 1. Install Docker
curl -fsSL https://get.docker.com | sh

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/openemr.git
cd openemr/docker/development-easy

# 3. Start all containers
docker compose up -d

# 4. Build assets (same as local setup)
cd ../..
docker run --rm -v $(pwd):/app -w /app composer:2 install --ignore-platform-reqs --no-interaction
docker compose -f docker/development-easy/docker-compose.yml exec openemr bash -c \
  "cd /var/www/localhost/htdocs/openemr && npm install && node_modules/.bin/gulp -b"

# 5. Load demo data
docker compose -f docker/development-easy/docker-compose.yml exec openemr \
  /root/devtools dev-reset-install-demodata
```

Access at **http://YOUR_DROPLET_IP:8300** — login: `admin` / `pass`

**Updating after code changes:**
```bash
ssh root@YOUR_DROPLET_IP
cd openemr
git pull
docker compose -f docker/development-easy/docker-compose.yml restart openemr
```

### Contributors

This project exists thanks to all the people who have contributed. [[Contribute]](CONTRIBUTING.md).
<a href="https://github.com/openemr/openemr/graphs/contributors"><img src="https://opencollective.com/openemr/contributors.svg?width=890" /></a>


### Sponsors

Thanks to our [ONC Certification Major Sponsors](https://www.open-emr.org/wiki/index.php/OpenEMR_Certification_Stage_III_Meaningful_Use#Major_sponsors)!


### License

[GNU GPL](LICENSE)
