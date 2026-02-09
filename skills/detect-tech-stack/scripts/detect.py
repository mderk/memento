#!/usr/bin/env python3
"""
Tech Stack Detection Script

Analyzes project structure and dependency files to detect frameworks,
databases, test frameworks, and libraries.

Usage:
    python detect.py [project_path]

Output:
    JSON object with detected technologies
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any


class TechStackDetector:
    """Detects project tech stack from dependency files and structure."""

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path).resolve()
        self.result: Dict[str, Any] = {
            "project_name": self.project_path.name,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "backend": {},
            "backends": [],  # For multiple backend support
            "has_multiple_backends": False,
            "frontend": {},
            "database": {},
            "testing": {},
            "libraries": {},
            "structure": {}
        }
        self.subdirs: List[str] = []
        self.all_js_deps: Dict[str, str] = {}
        self.all_py_content: str = ""

    def _discover_subdirs(self) -> List[str]:
        """Discover directories containing dependency files, up to 2 levels deep."""
        dep_files = {"package.json", "requirements.txt", "pyproject.toml",
                     "Pipfile", "go.mod", "Gemfile", "composer.json",
                     "pom.xml", "build.gradle"}
        found = {""}
        for child in self.project_path.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                if any((child / f).exists() for f in dep_files):
                    found.add(child.name)
                for grandchild in child.iterdir():
                    if grandchild.is_dir() and not grandchild.name.startswith("."):
                        if any((grandchild / f).exists() for f in dep_files):
                            found.add(f"{child.name}/{grandchild.name}")
        return sorted(found, key=lambda x: (len(x), x))

    def _collect_all_deps(self) -> tuple:
        """Collect merged dependency maps from all subdirs.

        Returns (merged_js_deps, merged_python_content).
        """
        js_deps: Dict[str, str] = {}
        py_content = ""
        for subdir in self.subdirs:
            # JS
            path = f"{subdir}/package.json" if subdir else "package.json"
            pkg = self._read_json(path)
            if pkg:
                js_deps.update(pkg.get("dependencies", {}))
                js_deps.update(pkg.get("devDependencies", {}))
            # Python
            for rf in ["requirements.txt", "pyproject.toml", "Pipfile"]:
                path = f"{subdir}/{rf}" if subdir else rf
                content = self._read_file(path)
                if content:
                    py_content += "\n" + content
        return js_deps, py_content

    def detect_all(self) -> Dict[str, Any]:
        """Run all detection methods.

        Order matters:
        - detect_backend() must run first (detect_testing reads self.result["backend"],
          detect_structure reads self.result["has_multiple_backends"])
        - detect_structure() must run last (uses has_multiple_backends and self.subdirs)
        """
        self.subdirs = self._discover_subdirs()
        self.all_js_deps, self.all_py_content = self._collect_all_deps()
        self.detect_backend()
        self.detect_frontend()
        self.detect_database()
        self.detect_testing()
        self.detect_libraries()
        self.detect_structure()  # after backend (uses has_multiple_backends)
        return self.result

    def detect_backend(self):
        """Detect ALL backend frameworks (supports multiple backends)."""
        backends = []

        # Use discovered subdirs instead of hardcoded list
        # Track dirs where we already found a backend to avoid duplicates from same dir
        found_python_dirs = set()
        found_js_dirs = set()

        # Python frameworks - check all subdirs
        requirements_files = [
            "requirements.txt", "pyproject.toml", "Pipfile"
        ]
        for subdir in self.subdirs:
            if subdir in found_python_dirs:
                continue
            for req_file in requirements_files:
                path = f"{subdir}/{req_file}" if subdir else req_file
                content = self._read_file(path)
                if content:
                    backend = self._detect_python_backend(content)
                    if backend:
                        backend["dir"] = subdir or "."
                        backends.append(backend)
                        found_python_dirs.add(subdir)
                        break

        # JavaScript/TypeScript frameworks - check all subdirs
        for subdir in self.subdirs:
            if subdir in found_js_dirs:
                continue
            path = f"{subdir}/package.json" if subdir else "package.json"
            package_json = self._read_json(path)
            if package_json:
                backend = self._detect_js_backend(package_json, subdir or ".")
                if backend:
                    backend["dir"] = subdir or "."
                    backends.append(backend)
                    found_js_dirs.add(subdir)

        # Go frameworks - check all subdirs
        for subdir in self.subdirs:
            path = f"{subdir}/go.mod" if subdir else "go.mod"
            go_mod = self._read_file(path)
            if go_mod:
                backend = self._detect_go_backend(go_mod)
                if backend:
                    backend["dir"] = subdir or "."
                    backends.append(backend)

        # Ruby frameworks - check all subdirs
        for subdir in self.subdirs:
            path = f"{subdir}/Gemfile" if subdir else "Gemfile"
            gemfile = self._read_file(path)
            if gemfile:
                backend = self._detect_ruby_backend(gemfile)
                if backend:
                    backend["dir"] = subdir or "."
                    backends.append(backend)

        # Java frameworks - check all subdirs
        for subdir in self.subdirs:
            for build_file in ["pom.xml", "build.gradle"]:
                path = f"{subdir}/{build_file}" if subdir else build_file
                content = self._read_file(path)
                if content:
                    backend = self._detect_java_backend(content)
                    if backend:
                        backend["dir"] = subdir or "."
                        backends.append(backend)
                        break

        # PHP frameworks - check all subdirs
        for subdir in self.subdirs:
            path = f"{subdir}/composer.json" if subdir else "composer.json"
            composer_json = self._read_json(path)
            if composer_json:
                backend = self._detect_php_backend(composer_json)
                if backend:
                    backend["dir"] = subdir or "."
                    backends.append(backend)

        # Set results based on number of backends found
        if len(backends) == 0:
            self.result["backend"] = {"has_backend": False}
            self.result["has_multiple_backends"] = False
        elif len(backends) == 1:
            self.result["backend"] = backends[0]
            self.result["has_multiple_backends"] = False
        else:
            # Multiple backends: primary + list
            self.result["backend"] = backends[0]  # Primary backend
            self.result["backends"] = backends     # All backends
            self.result["has_multiple_backends"] = True

    def detect_frontend(self):
        """Detect frontend framework."""
        # Check all discovered subdirs
        package_json = None
        frontend_dir = "."

        for subdir in self.subdirs:
            path = f"{subdir}/package.json" if subdir else "package.json"
            package_json = self._read_json(path)
            if package_json:
                frontend_dir = subdir or "."
                break

        if not package_json:
            self.result["frontend"] = {"has_frontend": False}
            return

        deps = {**package_json.get("dependencies", {}),
                **package_json.get("devDependencies", {})}

        # React
        if "react" in deps:
            frontend = {
                "framework": "React",
                "version": self._extract_version(deps.get("react", "")),
                "has_frontend": True,
                "dir": frontend_dir
            }
            # Check for meta-frameworks
            if "next" in deps:
                frontend["meta_framework"] = "Next.js"
                frontend["meta_version"] = self._extract_version(deps.get("next", ""))
            elif "gatsby" in deps:
                frontend["meta_framework"] = "Gatsby"
                frontend["meta_version"] = self._extract_version(deps.get("gatsby", ""))
            elif "@remix-run/react" in deps:
                frontend["meta_framework"] = "Remix"
            self.result["frontend"] = frontend
            return

        # Vue
        if "vue" in deps:
            frontend = {
                "framework": "Vue",
                "version": self._extract_version(deps.get("vue", "")),
                "has_frontend": True
            }
            if "nuxt" in deps:
                frontend["meta_framework"] = "Nuxt.js"
                frontend["meta_version"] = self._extract_version(deps.get("nuxt", ""))
            self.result["frontend"] = frontend
            return

        # Angular
        if "@angular/core" in deps:
            self.result["frontend"] = {
                "framework": "Angular",
                "version": self._extract_version(deps.get("@angular/core", "")),
                "has_frontend": True
            }
            return

        # Svelte
        if "svelte" in deps:
            frontend = {
                "framework": "Svelte",
                "version": self._extract_version(deps.get("svelte", "")),
                "has_frontend": True
            }
            if "@sveltejs/kit" in deps:
                frontend["meta_framework"] = "SvelteKit"
                frontend["meta_version"] = self._extract_version(deps.get("@sveltejs/kit", ""))
            self.result["frontend"] = frontend
            return

        # Vanilla JS with bundler
        if "vite" in deps or "webpack" in deps:
            self.result["frontend"] = {
                "framework": "Vanilla JS",
                "bundler": "Vite" if "vite" in deps else "Webpack",
                "has_frontend": True
            }
            return

        self.result["frontend"] = {"has_frontend": False}

    def detect_database(self):
        """Detect database systems from dependencies, docker-compose, and ORM config files."""
        databases = []
        cache_db = None
        detected_orm = None

        # Use merged deps from all subdirs
        py_deps = self.all_py_content
        js_deps = self.all_js_deps

        # Python database drivers
        if "psycopg2" in py_deps or "psycopg" in py_deps:
            databases.append("PostgreSQL")
        if "mysqlclient" in py_deps or "pymysql" in py_deps:
            databases.append("MySQL")
        if "pymongo" in py_deps:
            databases.append("MongoDB")
        if "redis" in py_deps:
            cache_db = "Redis"

        # JavaScript database drivers (from merged deps)
        if "pg" in js_deps:
            databases.append("PostgreSQL")
        if "mysql2" in js_deps or "mysql" in js_deps:
            databases.append("MySQL")
        if "mongodb" in js_deps:
            databases.append("MongoDB")
        if "sqlite3" in js_deps:
            databases.append("SQLite")
        if "redis" in js_deps or "ioredis" in js_deps:
            cache_db = "Redis"

        # Go dependencies - check all subdirs
        for subdir in self.subdirs:
            path = f"{subdir}/go.mod" if subdir else "go.mod"
            go_mod = self._read_file(path) or ""
            if "github.com/lib/pq" in go_mod:
                databases.append("PostgreSQL")
            if "github.com/go-sql-driver/mysql" in go_mod:
                databases.append("MySQL")
            if "go.mongodb.org/mongo-driver" in go_mod:
                databases.append("MongoDB")
            if "github.com/redis/go-redis" in go_mod:
                cache_db = "Redis"

        # Check docker-compose.yml
        docker_compose = self._read_file("docker-compose.yml") or ""
        if "postgres:" in docker_compose or "postgresql:" in docker_compose:
            databases.append("PostgreSQL")
        if "mysql:" in docker_compose:
            databases.append("MySQL")
        if "mongo:" in docker_compose or "mongodb:" in docker_compose:
            databases.append("MongoDB")
        if "redis:" in docker_compose:
            cache_db = "Redis"

        # ORM config file parsing for database detection
        for subdir in self.subdirs:
            prefix = f"{subdir}/" if subdir else ""

            # Prisma: prisma/schema.prisma
            prisma_schema = self._read_file(f"{prefix}prisma/schema.prisma")
            if prisma_schema:
                detected_orm = detected_orm or "Prisma"
                if re.search(r'provider\s*=\s*"postgresql"', prisma_schema):
                    databases.append("PostgreSQL")
                elif re.search(r'provider\s*=\s*"mysql"', prisma_schema):
                    databases.append("MySQL")
                elif re.search(r'provider\s*=\s*"sqlite"', prisma_schema):
                    databases.append("SQLite")
                elif re.search(r'provider\s*=\s*"mongodb"', prisma_schema):
                    databases.append("MongoDB")

            # Django: settings.py
            for settings_path in [f"{prefix}settings.py",
                                  f"{prefix}*/settings.py"]:
                # For glob patterns, use _find_files helper
                if "*" in settings_path:
                    continue  # handled below
                settings = self._read_file(settings_path)
                if settings:
                    if "django.db.backends.postgresql" in settings:
                        databases.append("PostgreSQL")
                        detected_orm = detected_orm or "Django ORM"
                    elif "django.db.backends.mysql" in settings:
                        databases.append("MySQL")
                        detected_orm = detected_orm or "Django ORM"
                    elif "django.db.backends.sqlite3" in settings:
                        databases.append("SQLite")
                        detected_orm = detected_orm or "Django ORM"

            # Django nested settings (one level deep)
            if subdir == "" or subdir:
                base = self.project_path / prefix.rstrip("/") if prefix else self.project_path
                if base.is_dir():
                    for child in base.iterdir():
                        if child.is_dir() and not child.name.startswith("."):
                            settings_file = child / "settings.py"
                            if settings_file.exists():
                                settings = self._read_file(
                                    f"{prefix}{child.name}/settings.py")
                                if settings:
                                    if "django.db.backends.postgresql" in settings:
                                        databases.append("PostgreSQL")
                                        detected_orm = detected_orm or "Django ORM"
                                    elif "django.db.backends.mysql" in settings:
                                        databases.append("MySQL")
                                        detected_orm = detected_orm or "Django ORM"

            # Rails: config/database.yml
            db_yml = self._read_file(f"{prefix}config/database.yml")
            if db_yml:
                if "adapter: postgresql" in db_yml or "adapter: postgres" in db_yml:
                    databases.append("PostgreSQL")
                    detected_orm = detected_orm or "ActiveRecord"
                elif "adapter: mysql2" in db_yml:
                    databases.append("MySQL")
                    detected_orm = detected_orm or "ActiveRecord"

            # Spring Boot: application.properties / application.yml
            for cfg in ["src/main/resources/application.properties",
                        "src/main/resources/application.yml"]:
                spring_cfg = self._read_file(f"{prefix}{cfg}")
                if spring_cfg:
                    if "jdbc:postgresql://" in spring_cfg:
                        databases.append("PostgreSQL")
                    elif "jdbc:mysql://" in spring_cfg:
                        databases.append("MySQL")

            # Alembic: alembic.ini
            alembic_ini = self._read_file(f"{prefix}alembic.ini")
            if alembic_ini:
                if "postgresql://" in alembic_ini:
                    databases.append("PostgreSQL")
                    detected_orm = detected_orm or "SQLAlchemy"
                elif "mysql://" in alembic_ini:
                    databases.append("MySQL")
                    detected_orm = detected_orm or "SQLAlchemy"

        # Laravel: .env
        env_file = self._read_file(".env")
        if env_file:
            if "DB_CONNECTION=pgsql" in env_file:
                databases.append("PostgreSQL")
            elif "DB_CONNECTION=mysql" in env_file:
                databases.append("MySQL")
            if re.search(r"DATABASE_URL\s*=\s*postgresql://", env_file):
                databases.append("PostgreSQL")

        # ORM detection from dependencies (if not yet detected from config)
        if not detected_orm:
            # JS ORMs
            if "prisma" in js_deps or "@prisma/client" in js_deps:
                detected_orm = "Prisma"
            elif "typeorm" in js_deps:
                detected_orm = "TypeORM"
            elif "sequelize" in js_deps:
                detected_orm = "Sequelize"
            elif "drizzle-orm" in js_deps:
                detected_orm = "Drizzle"
            elif "mongoose" in js_deps:
                detected_orm = "Mongoose"
            # Python ORMs
            elif "sqlalchemy" in py_deps.lower():
                detected_orm = "SQLAlchemy"
            elif "tortoise-orm" in py_deps.lower():
                detected_orm = "Tortoise ORM"
            elif "django" in py_deps.lower():
                detected_orm = "Django ORM"
            elif "peewee" in py_deps.lower():
                detected_orm = "Peewee"

        # Deduplicate preserving order
        databases = list(dict.fromkeys(databases))

        self.result["database"] = {
            "primary": databases[0] if databases else None,
            "orm": detected_orm,
            "cache": cache_db
        }

    def detect_testing(self):
        """Detect test frameworks."""
        frameworks = []

        # Use discovered subdirs
        # Python test frameworks - check all locations
        for subdir in self.subdirs:
            for req_file in ["requirements.txt", "pyproject.toml"]:
                path = f"{subdir}/{req_file}" if subdir else req_file
                content = self._read_file(path) or ""
                if "pytest" in content and "pytest" not in frameworks:
                    frameworks.append("pytest")

        # JavaScript test frameworks - check all locations
        for subdir in self.subdirs:
            path = f"{subdir}/package.json" if subdir else "package.json"
            package_json = self._read_json(path)
            if package_json:
                deps = {**package_json.get("dependencies", {}),
                        **package_json.get("devDependencies", {})}
                if "jest" in deps and "jest" not in frameworks:
                    frameworks.append("jest")
                if "vitest" in deps and "vitest" not in frameworks:
                    frameworks.append("vitest")
                if "@playwright/test" in deps and "playwright" not in frameworks:
                    frameworks.append("playwright")
                if "cypress" in deps and "cypress" not in frameworks:
                    frameworks.append("cypress")
                if "mocha" in deps and "mocha" not in frameworks:
                    frameworks.append("mocha")

        # Go test frameworks - check all subdirs
        for subdir in self.subdirs:
            path = f"{subdir}/go.mod" if subdir else "go.mod"
            go_mod = self._read_file(path) or ""
            if "github.com/stretchr/testify" in go_mod and "testify" not in frameworks:
                frameworks.append("testify")
        if self.result["backend"].get("language") == "Go":
            if "testing" not in frameworks:
                frameworks.append("testing")  # built-in

        # Ruby test frameworks - check all subdirs
        for subdir in self.subdirs:
            path = f"{subdir}/Gemfile" if subdir else "Gemfile"
            gemfile = self._read_file(path) or ""
            if "rspec" in gemfile and "rspec" not in frameworks:
                frameworks.append("rspec")

        has_e2e = any(f in ["playwright", "cypress"] for f in frameworks)

        self.result["testing"] = {
            "frameworks": frameworks,
            "has_tests": len(frameworks) > 0,
            "has_e2e_tests": has_e2e
        }

    def detect_libraries(self):
        """Detect additional libraries organized by category across all languages."""
        categories: Dict[str, List[str]] = {}

        js_deps = self.all_js_deps
        py_content = self.all_py_content.lower()

        # --- JS/TS package detection ---
        js_lookup = {
            # orm
            "prisma": ("orm", "Prisma"), "@prisma/client": ("orm", "Prisma"),
            "typeorm": ("orm", "TypeORM"), "sequelize": ("orm", "Sequelize"),
            "drizzle-orm": ("orm", "Drizzle"), "mongoose": ("orm", "Mongoose"),
            "knex": ("orm", "Knex"),
            # ui
            "@headlessui/react": ("ui", "Headless UI"),
            "@shadcn/ui": ("ui", "shadcn/ui"),
            "@mui/material": ("ui", "Material-UI"),
            "@chakra-ui/react": ("ui", "Chakra UI"),
            "antd": ("ui", "Ant Design"),
            # css
            "tailwindcss": ("css", "Tailwind CSS"),
            "styled-components": ("css", "styled-components"),
            "@emotion/react": ("css", "Emotion"),
            "sass": ("css", "Sass"),
            # state_management
            "redux": ("state_management", "Redux"),
            "@reduxjs/toolkit": ("state_management", "Redux Toolkit"),
            "zustand": ("state_management", "Zustand"),
            "mobx": ("state_management", "MobX"),
            "recoil": ("state_management", "Recoil"),
            "jotai": ("state_management", "Jotai"),
            "pinia": ("state_management", "Pinia"),
            "vuex": ("state_management", "Vuex"),
            # forms
            "formik": ("forms", "Formik"),
            "react-hook-form": ("forms", "React Hook Form"),
            "@tanstack/react-form": ("forms", "TanStack Form"),
            # validation
            "zod": ("validation", "zod"),
            "yup": ("validation", "yup"),
            "joi": ("validation", "joi"),
            "class-validator": ("validation", "class-validator"),
            "superstruct": ("validation", "superstruct"),
            "valibot": ("validation", "valibot"),
            # charts
            "recharts": ("charts", "recharts"),
            "d3": ("charts", "D3"),
            "chart.js": ("charts", "Chart.js"),
            "@nivo/core": ("charts", "Nivo"),
            "highcharts": ("charts", "Highcharts"),
            "plotly.js": ("charts", "Plotly"),
            # i18n
            "i18next": ("i18n", "i18next"),
            "react-intl": ("i18n", "react-intl"),
            "vue-i18n": ("i18n", "vue-i18n"),
            "@formatjs/intl": ("i18n", "FormatJS"),
            # auth
            "next-auth": ("auth", "next-auth"),
            "@auth/core": ("auth", "Auth.js"),
            "passport": ("auth", "Passport"),
            "jsonwebtoken": ("auth", "jsonwebtoken"),
            # api_client
            "axios": ("api_client", "axios"),
            "got": ("api_client", "got"),
            "ky": ("api_client", "ky"),
            "@tanstack/react-query": ("api_client", "TanStack Query"),
            "swr": ("api_client", "SWR"),
            "@trpc/client": ("api_client", "tRPC"),
            # realtime
            "socket.io": ("realtime", "socket.io"),
            "socket.io-client": ("realtime", "socket.io"),
            "pusher-js": ("realtime", "Pusher"),
            "@supabase/realtime-js": ("realtime", "Supabase Realtime"),
            # search
            "@elastic/elasticsearch": ("search", "Elasticsearch"),
            "algoliasearch": ("search", "Algolia"),
            "meilisearch": ("search", "Meilisearch"),
            # task_queue
            "bull": ("task_queue", "Bull"),
            "bullmq": ("task_queue", "BullMQ"),
            "bee-queue": ("task_queue", "Bee-Queue"),
            # logging
            "winston": ("logging", "Winston"),
            "pino": ("logging", "Pino"),
            "bunyan": ("logging", "Bunyan"),
        }

        # Handle @radix-ui/* prefix
        for dep_name in js_deps:
            if dep_name.startswith("@radix-ui/"):
                cat = "ui"
                lib = "Radix UI"
                if cat not in categories:
                    categories[cat] = []
                if lib not in categories[cat]:
                    categories[cat].append(lib)

        for dep_name, (cat, lib) in js_lookup.items():
            if dep_name in js_deps:
                if cat not in categories:
                    categories[cat] = []
                if lib not in categories[cat]:
                    categories[cat].append(lib)

        # --- Python package detection ---
        py_lookup = {
            # orm
            "sqlalchemy": ("orm", "SQLAlchemy"),
            "tortoise-orm": ("orm", "Tortoise ORM"),
            "peewee": ("orm", "Peewee"),
            "mongoengine": ("orm", "MongoEngine"),
            # scientific
            "numpy": ("scientific", "numpy"),
            "scipy": ("scientific", "scipy"),
            "sympy": ("scientific", "sympy"),
            "pandas": ("scientific", "pandas"),
            # ml
            "torch": ("ml", "torch"),
            "pytorch": ("ml", "torch"),
            "tensorflow": ("ml", "tensorflow"),
            "scikit-learn": ("ml", "scikit-learn"),
            "keras": ("ml", "keras"),
            "xgboost": ("ml", "xgboost"),
            "lightgbm": ("ml", "lightgbm"),
            "transformers": ("ml", "transformers"),
            # validation
            "pydantic": ("validation", "pydantic"),
            "marshmallow": ("validation", "marshmallow"),
            "cerberus": ("validation", "cerberus"),
            "attrs": ("validation", "attrs"),
            # http_client
            "requests": ("http_client", "requests"),
            "httpx": ("http_client", "httpx"),
            "aiohttp": ("http_client", "aiohttp"),
            "urllib3": ("http_client", "urllib3"),
            # task_queue
            "celery": ("task_queue", "celery"),
            "dramatiq": ("task_queue", "dramatiq"),
            "huey": ("task_queue", "huey"),
            "rq": ("task_queue", "rq"),
            # auth
            "django-allauth": ("auth", "django-allauth"),
            "python-jose": ("auth", "python-jose"),
            "pyjwt": ("auth", "PyJWT"),
            "authlib": ("auth", "Authlib"),
            # charts
            "matplotlib": ("charts", "matplotlib"),
            "plotly": ("charts", "plotly"),
            "seaborn": ("charts", "seaborn"),
            "bokeh": ("charts", "bokeh"),
            # logging
            "loguru": ("logging", "loguru"),
            "structlog": ("logging", "structlog"),
            # cli
            "click": ("cli", "click"),
            "typer": ("cli", "typer"),
            "rich": ("cli", "rich"),
            # search
            "elasticsearch": ("search", "elasticsearch"),
            "opensearch-py": ("search", "opensearch-py"),
        }

        # Django implies ORM
        if "django" in py_content:
            if "orm" not in categories:
                categories["orm"] = []
            if "Django ORM" not in categories["orm"]:
                categories["orm"].append("Django ORM")

        for pkg, (cat, lib) in py_lookup.items():
            if pkg in py_content:
                if cat not in categories:
                    categories[cat] = []
                if lib not in categories[cat]:
                    categories[cat].append(lib)

        # --- Go package detection ---
        for subdir in self.subdirs:
            path = f"{subdir}/go.mod" if subdir else "go.mod"
            go_mod = self._read_file(path) or ""
            if not go_mod:
                continue

            go_lookup = {
                "gorm.io/gorm": ("orm", "GORM"),
                "entgo.io/ent": ("orm", "Ent"),
                "github.com/jmoiron/sqlx": ("orm", "sqlx"),
                "github.com/go-playground/validator": ("validation", "go-playground/validator"),
                "go.uber.org/zap": ("logging", "Zap"),
                "github.com/sirupsen/logrus": ("logging", "Logrus"),
                "log/slog": ("logging", "slog"),
                "github.com/go-resty/resty": ("http_client", "Resty"),
                "github.com/golang-jwt/jwt": ("auth", "golang-jwt"),
                "google.golang.org/grpc": ("grpc", "gRPC"),
                "github.com/spf13/viper": ("config", "Viper"),
            }
            for mod, (cat, lib) in go_lookup.items():
                if mod in go_mod:
                    if cat not in categories:
                        categories[cat] = []
                    if lib not in categories[cat]:
                        categories[cat].append(lib)

        # --- Ruby gem detection ---
        for subdir in self.subdirs:
            path = f"{subdir}/Gemfile" if subdir else "Gemfile"
            gemfile = self._read_file(path) or ""
            if not gemfile:
                continue

            ruby_lookup = {
                "devise": ("auth", "Devise"),
                "omniauth": ("auth", "OmniAuth"),
                "jwt": ("auth", "jwt"),
                "sidekiq": ("task_queue", "Sidekiq"),
                "delayed_job": ("task_queue", "Delayed Job"),
                "resque": ("task_queue", "Resque"),
                "good_job": ("task_queue", "GoodJob"),
                "searchkick": ("search", "Searchkick"),
                "ransack": ("search", "Ransack"),
                "elasticsearch-model": ("search", "elasticsearch-model"),
                "grape": ("api", "Grape"),
                "graphql-ruby": ("api", "graphql-ruby"),
                "jbuilder": ("api", "Jbuilder"),
                "kaminari": ("pagination", "Kaminari"),
                "will_paginate": ("pagination", "will_paginate"),
                "pagy": ("pagination", "Pagy"),
                "carrierwave": ("file_upload", "CarrierWave"),
                "shrine": ("file_upload", "Shrine"),
                "active_storage": ("file_upload", "Active Storage"),
            }
            for gem, (cat, lib) in ruby_lookup.items():
                if gem in gemfile:
                    if cat not in categories:
                        categories[cat] = []
                    if lib not in categories[cat]:
                        categories[cat].append(lib)

        # --- Java detection (pom.xml / build.gradle) ---
        for subdir in self.subdirs:
            for build_file in ["pom.xml", "build.gradle"]:
                path = f"{subdir}/{build_file}" if subdir else build_file
                content = self._read_file(path) or ""
                if not content:
                    continue

                java_lookup = {
                    "hibernate": ("orm", "Hibernate"),
                    "mybatis": ("orm", "MyBatis"),
                    "spring-data-jpa": ("orm", "Spring Data JPA"),
                    "spring-security": ("auth", "Spring Security"),
                    "keycloak": ("auth", "Keycloak"),
                    "spring-kafka": ("messaging", "Spring Kafka"),
                    "spring-amqp": ("messaging", "Spring AMQP"),
                    "spring-data-elasticsearch": ("search", "Spring Data Elasticsearch"),
                }
                for artifact, (cat, lib) in java_lookup.items():
                    if artifact in content:
                        if cat not in categories:
                            categories[cat] = []
                        if lib not in categories[cat]:
                            categories[cat].append(lib)

        # --- PHP detection (composer.json) ---
        for subdir in self.subdirs:
            path = f"{subdir}/composer.json" if subdir else "composer.json"
            composer = self._read_json(path)
            if not composer:
                continue
            php_deps = {**composer.get("require", {}),
                        **composer.get("require-dev", {})}

            php_lookup = {
                "doctrine/orm": ("orm", "Doctrine"),
                "illuminate/database": ("orm", "Eloquent"),
                "laravel/sanctum": ("auth", "Laravel Sanctum"),
                "laravel/passport": ("auth", "Laravel Passport"),
                "tymon/jwt-auth": ("auth", "tymon/jwt-auth"),
                "laravel/horizon": ("task_queue", "Laravel Horizon"),
                "php-amqplib/php-amqplib": ("task_queue", "php-amqplib"),
            }
            for pkg_name, (cat, lib) in php_lookup.items():
                if pkg_name in php_deps:
                    if cat not in categories:
                        categories[cat] = []
                    if lib not in categories[cat]:
                        categories[cat].append(lib)

        self.result["libraries"] = categories

    def detect_structure(self):
        """Detect project structure (monorepo, Docker, CI/CD)."""
        structure = {
            "is_monorepo": False,
            "has_docker": False,
            "has_ci_cd": False,
            "ci_platform": None,
            "deployment_platform": None
        }

        # Monorepo detection - explicit config files
        if (self._file_exists("lerna.json") or
            self._file_exists("pnpm-workspace.yaml") or
            self._file_exists("turbo.json")):
            structure["is_monorepo"] = True

        # Nx
        if self._file_exists("nx.json"):
            structure["is_monorepo"] = True

        # Yarn/npm workspaces
        root_pkg = self._read_json("package.json")
        if root_pkg and "workspaces" in root_pkg:
            structure["is_monorepo"] = True

        # Heuristic: multiple backends already detected
        if self.result.get("has_multiple_backends"):
            structure["is_monorepo"] = True

        # Heuristic: multiple package.json in different dirs
        pkg_dirs = [s for s in self.subdirs
                    if s and self._file_exists(f"{s}/package.json")]
        if len(pkg_dirs) >= 2:
            structure["is_monorepo"] = True

        # Heuristic: mixed language stacks in different dirs
        dep_dirs = [s for s in self.subdirs if s]
        if len(dep_dirs) >= 2:
            structure["is_monorepo"] = True

        # Docker detection
        if (self._file_exists("Dockerfile") or
            self._file_exists("docker-compose.yml")):
            structure["has_docker"] = True

        # CI/CD detection
        if self._file_exists(".github/workflows"):
            structure["has_ci_cd"] = True
            structure["ci_platform"] = "GitHub Actions"
        elif self._file_exists(".gitlab-ci.yml"):
            structure["has_ci_cd"] = True
            structure["ci_platform"] = "GitLab CI"
        elif self._file_exists(".circleci/config.yml"):
            structure["has_ci_cd"] = True
            structure["ci_platform"] = "CircleCI"

        # Deployment platform
        if self._file_exists("vercel.json"):
            structure["deployment_platform"] = "Vercel"
        elif self._file_exists("netlify.toml"):
            structure["deployment_platform"] = "Netlify"
        elif self._file_exists("render.yaml"):
            structure["deployment_platform"] = "Render"

        self.result["structure"] = structure

    # Helper methods for specific language detections

    def _detect_python_backend(self, content: str) -> Optional[Dict]:
        """Detect Python backend framework."""
        if match := re.search(r"django\s*[>=<~!]+\s*([\d.]+)", content, re.I):
            return {
                "framework": "Django",
                "version": match.group(1),
                "language": "Python",
                "has_backend": True
            }
        if match := re.search(r"fastapi\s*[>=<~!]+\s*([\d.]+)", content, re.I):
            return {
                "framework": "FastAPI",
                "version": match.group(1),
                "language": "Python",
                "has_backend": True
            }
        if match := re.search(r"flask\s*[>=<~!]+\s*([\d.]+)", content, re.I):
            return {
                "framework": "Flask",
                "version": match.group(1),
                "language": "Python",
                "has_backend": True
            }
        if "django" in content.lower():
            return {"framework": "Django", "language": "Python", "has_backend": True}
        if "fastapi" in content.lower():
            return {"framework": "FastAPI", "language": "Python", "has_backend": True}
        if "flask" in content.lower():
            return {"framework": "Flask", "language": "Python", "has_backend": True}
        return None

    def _detect_js_backend(self, package_json: Dict, base_dir: str = ".") -> Optional[Dict]:
        """Detect JavaScript/TypeScript backend framework."""
        deps = {**package_json.get("dependencies", {}),
                **package_json.get("devDependencies", {})}

        if "express" in deps:
            return {
                "framework": "Express.js",
                "version": self._extract_version(deps["express"]),
                "language": "JavaScript",
                "has_backend": True
            }
        if "@nestjs/core" in deps:
            return {
                "framework": "NestJS",
                "version": self._extract_version(deps["@nestjs/core"]),
                "language": "TypeScript",
                "has_backend": True
            }
        if "koa" in deps:
            return {
                "framework": "Koa",
                "version": self._extract_version(deps["koa"]),
                "language": "JavaScript",
                "has_backend": True
            }
        if "fastify" in deps:
            return {
                "framework": "Fastify",
                "version": self._extract_version(deps["fastify"]),
                "language": "JavaScript",
                "has_backend": True
            }
        # Next.js with API routes
        if "next" in deps:
            # Check for API routes directory (most reliable indicator)
            has_api_dir = (
                self._file_exists(f"{base_dir}/pages/api") or
                self._file_exists(f"{base_dir}/app/api") or
                self._file_exists(f"{base_dir}/src/pages/api") or
                self._file_exists(f"{base_dir}/src/app/api")
            )
            # Fallback: check for server-side libraries
            has_server_libs = any([
                "prisma" in deps, "@prisma/client" in deps,
                "pg" in deps, "mysql2" in deps, "mongodb" in deps,
                "mongoose" in deps, "drizzle-orm" in deps,
                "next-auth" in deps, "@auth/core" in deps,
            ])
            if has_api_dir or has_server_libs:
                return {
                    "framework": "Next.js",
                    "version": self._extract_version(deps["next"]),
                    "language": "TypeScript",
                    "has_backend": True,
                    "type": "api_routes"
                }
        return None

    def _detect_go_backend(self, content: str) -> Optional[Dict]:
        """Detect Go backend framework."""
        if "github.com/gin-gonic/gin" in content:
            version = self._extract_go_version(content, "gin")
            return {"framework": "Gin", "version": version, "language": "Go", "has_backend": True}
        if "github.com/gofiber/fiber" in content:
            version = self._extract_go_version(content, "fiber")
            return {"framework": "Fiber", "version": version, "language": "Go", "has_backend": True}
        if "github.com/labstack/echo" in content:
            version = self._extract_go_version(content, "echo")
            return {"framework": "Echo", "version": version, "language": "Go", "has_backend": True}
        return None

    def _detect_ruby_backend(self, content: str) -> Optional[Dict]:
        """Detect Ruby backend framework."""
        if match := re.search(r"gem ['\"]rails['\"],\s*['\"]~>\s*([\d.]+)", content):
            return {"framework": "Rails", "version": match.group(1), "language": "Ruby", "has_backend": True}
        if "gem 'rails'" in content or 'gem "rails"' in content:
            return {"framework": "Rails", "language": "Ruby", "has_backend": True}
        if "gem 'sinatra'" in content or 'gem "sinatra"' in content:
            return {"framework": "Sinatra", "language": "Ruby", "has_backend": True}
        return None

    def _detect_java_backend(self, content: str) -> Optional[Dict]:
        """Detect Java backend framework."""
        if "spring-boot-starter" in content:
            return {"framework": "Spring Boot", "language": "Java", "has_backend": True}
        if "quarkus" in content:
            return {"framework": "Quarkus", "language": "Java", "has_backend": True}
        if "micronaut" in content:
            return {"framework": "Micronaut", "language": "Java", "has_backend": True}
        return None

    def _detect_php_backend(self, composer_json: Dict) -> Optional[Dict]:
        """Detect PHP backend framework."""
        deps = composer_json.get("require", {})
        if "laravel/framework" in deps:
            return {"framework": "Laravel", "language": "PHP", "has_backend": True}
        if "symfony/symfony" in deps:
            return {"framework": "Symfony", "language": "PHP", "has_backend": True}
        return None

    # Utility methods

    def _read_file(self, filename: str) -> Optional[str]:
        """Read file content."""
        file_path = self.project_path / filename
        if file_path.exists() and file_path.is_file():
            try:
                return file_path.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def _read_json(self, filename: str) -> Optional[Dict]:
        """Read and parse JSON file."""
        content = self._read_file(filename)
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return None
        return None

    def _file_exists(self, path: str) -> bool:
        """Check if file or directory exists."""
        return (self.project_path / path).exists()

    def _extract_version(self, version_string: str) -> Optional[str]:
        """Extract version number from dependency string."""
        if match := re.search(r"(\d+\.\d+\.\d+)", version_string):
            return match.group(1)
        if match := re.search(r"(\d+\.\d+)", version_string):
            return match.group(1)
        return None

    def _extract_go_version(self, content: str, package: str) -> Optional[str]:
        """Extract version from go.mod."""
        pattern = rf"{package}.*v(\d+\.\d+\.\d+)"
        if match := re.search(pattern, content):
            return match.group(1)
        return None


def main():
    """Main entry point."""
    project_path = sys.argv[1] if len(sys.argv) > 1 else "."

    # Check if project path exists
    if not Path(project_path).exists():
        print(json.dumps({
            "status": "error",
            "message": f"Project path does not exist: {project_path}"
        }), file=sys.stderr)
        sys.exit(2)

    # Run detection
    detector = TechStackDetector(project_path)
    result = detector.detect_all()

    # Check if anything was detected
    if not any([
        result["backend"].get("has_backend"),
        result["frontend"].get("has_frontend"),
        result["database"].get("primary"),
        result["testing"].get("has_tests")
    ]):
        print(json.dumps({
            "status": "error",
            "message": "No dependency files found. Is this a code project?"
        }), file=sys.stderr)
        sys.exit(1)

    # Output success
    output = {
        "status": "success",
        "data": result
    }
    print(json.dumps(output, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
