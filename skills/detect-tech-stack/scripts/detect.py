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

    def detect_all(self) -> Dict[str, Any]:
        """Run all detection methods."""
        self.detect_backend()
        self.detect_frontend()
        self.detect_database()
        self.detect_testing()
        self.detect_libraries()
        self.detect_structure()
        return self.result

    def detect_backend(self):
        """Detect ALL backend frameworks (supports multiple backends)."""
        backends = []

        # Common subdirectories to check for multi-project setups
        subdirs = ["", "web", "client", "frontend", "server", "backend",
                   "api", "app", "src", "math_model", "services"]

        # Python frameworks - check root and subdirs
        requirements_files = [
            "requirements.txt", "pyproject.toml", "Pipfile"
        ]
        python_found = False
        for subdir in subdirs:
            if python_found:
                break
            for req_file in requirements_files:
                path = f"{subdir}/{req_file}" if subdir else req_file
                content = self._read_file(path)
                if content:
                    backend = self._detect_python_backend(content)
                    if backend:
                        backend["dir"] = subdir or "."
                        backends.append(backend)
                        python_found = True
                        break

        # JavaScript/TypeScript frameworks - check root and subdirs
        for subdir in subdirs:
            path = f"{subdir}/package.json" if subdir else "package.json"
            package_json = self._read_json(path)
            if package_json:
                backend = self._detect_js_backend(package_json, subdir or ".")
                if backend:
                    backend["dir"] = subdir or "."
                    backends.append(backend)
                    break  # Only first JS backend

        # Go frameworks
        go_mod = self._read_file("go.mod")
        if go_mod:
            backend = self._detect_go_backend(go_mod)
            if backend:
                backends.append(backend)

        # Ruby frameworks
        gemfile = self._read_file("Gemfile")
        if gemfile:
            backend = self._detect_ruby_backend(gemfile)
            if backend:
                backends.append(backend)

        # Java frameworks
        for build_file in ["pom.xml", "build.gradle"]:
            content = self._read_file(build_file)
            if content:
                backend = self._detect_java_backend(content)
                if backend:
                    backends.append(backend)
                    break  # Only one Java backend per project

        # PHP frameworks
        composer_json = self._read_json("composer.json")
        if composer_json:
            backend = self._detect_php_backend(composer_json)
            if backend:
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
        # Check root and common subdirectories
        subdirs = ["", "web", "client", "frontend", "app", "src"]
        package_json = None
        frontend_dir = "."

        for subdir in subdirs:
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
        """Detect database systems."""
        databases = []
        cache_db = None

        # Check Python dependencies
        requirements = self._read_file("requirements.txt") or ""
        pyproject = self._read_file("pyproject.toml") or ""
        py_deps = requirements + pyproject

        if "psycopg2" in py_deps or "psycopg" in py_deps:
            databases.append("PostgreSQL")
        if "mysqlclient" in py_deps or "pymysql" in py_deps:
            databases.append("MySQL")
        if "pymongo" in py_deps:
            databases.append("MongoDB")
        if "redis" in py_deps:
            cache_db = "Redis"

        # Check JavaScript dependencies
        package_json = self._read_json("package.json")
        if package_json:
            deps = {**package_json.get("dependencies", {}),
                    **package_json.get("devDependencies", {})}
            if "pg" in deps:
                databases.append("PostgreSQL")
            if "mysql2" in deps or "mysql" in deps:
                databases.append("MySQL")
            if "mongodb" in deps:
                databases.append("MongoDB")
            if "sqlite3" in deps:
                databases.append("SQLite")
            if "redis" in deps or "ioredis" in deps:
                cache_db = "Redis"

        # Check Go dependencies
        go_mod = self._read_file("go.mod") or ""
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

        # Deduplicate
        databases = list(set(databases))

        self.result["database"] = {
            "primary": databases[0] if databases else None,
            "cache": cache_db
        }

    def detect_testing(self):
        """Detect test frameworks."""
        frameworks = []

        # Common subdirectories
        subdirs = ["", "web", "client", "frontend", "server", "backend", "api"]

        # Python test frameworks - check all locations
        for subdir in subdirs:
            for req_file in ["requirements.txt", "pyproject.toml"]:
                path = f"{subdir}/{req_file}" if subdir else req_file
                content = self._read_file(path) or ""
                if "pytest" in content and "pytest" not in frameworks:
                    frameworks.append("pytest")

        # JavaScript test frameworks - check all locations
        for subdir in subdirs:
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

        # Go test frameworks
        go_mod = self._read_file("go.mod") or ""
        if "github.com/stretchr/testify" in go_mod:
            frameworks.append("testify")
        if self.result["backend"].get("language") == "Go":
            frameworks.append("testing")  # built-in

        # Ruby test frameworks
        gemfile = self._read_file("Gemfile") or ""
        if "rspec" in gemfile:
            frameworks.append("rspec")

        has_e2e = any(f in ["playwright", "cypress"] for f in frameworks)

        self.result["testing"] = {
            "frameworks": frameworks,
            "has_tests": len(frameworks) > 0,
            "has_e2e_tests": has_e2e
        }

    def detect_libraries(self):
        """Detect additional libraries (ORM, state management, etc.)."""
        libraries = {}

        package_json = self._read_json("package.json")
        if package_json:
            deps = {**package_json.get("dependencies", {}),
                    **package_json.get("devDependencies", {})}

            # State management
            if "redux" in deps:
                libraries["state_management"] = "Redux"
            elif "zustand" in deps:
                libraries["state_management"] = "Zustand"
            elif "mobx" in deps:
                libraries["state_management"] = "MobX"
            elif "recoil" in deps:
                libraries["state_management"] = "Recoil"

            # ORM (JavaScript)
            if "prisma" in deps:
                libraries["orm"] = "Prisma"
            elif "typeorm" in deps:
                libraries["orm"] = "TypeORM"
            elif "sequelize" in deps:
                libraries["orm"] = "Sequelize"
            elif "drizzle-orm" in deps:
                libraries["orm"] = "Drizzle"

            # UI libraries
            if "@mui/material" in deps:
                libraries["ui_library"] = "Material-UI"
            elif "@chakra-ui/react" in deps:
                libraries["ui_library"] = "Chakra UI"
            elif "antd" in deps:
                libraries["ui_library"] = "Ant Design"
            elif "tailwindcss" in deps:
                libraries["ui_library"] = "Tailwind CSS"

            # API client
            if "axios" in deps:
                libraries["api_client"] = "axios"
            elif "got" in deps:
                libraries["api_client"] = "got"

        # Python ORM
        requirements = self._read_file("requirements.txt") or ""
        if "sqlalchemy" in requirements:
            libraries["orm"] = "SQLAlchemy"
        elif "tortoise-orm" in requirements:
            libraries["orm"] = "Tortoise ORM"

        self.result["libraries"] = libraries

    def detect_structure(self):
        """Detect project structure (monorepo, Docker, CI/CD)."""
        structure = {
            "is_monorepo": False,
            "has_docker": False,
            "has_ci_cd": False,
            "ci_platform": None,
            "deployment_platform": None
        }

        # Monorepo detection
        if (self._file_exists("lerna.json") or
            self._file_exists("pnpm-workspace.yaml") or
            self._file_exists("turbo.json")):
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
        if match := re.search(r"django[>=<~]=*([\d.]+)", content, re.I):
            return {
                "framework": "Django",
                "version": match.group(1),
                "language": "Python",
                "has_backend": True
            }
        if match := re.search(r"fastapi[>=<~]=*([\d.]+)", content, re.I):
            return {
                "framework": "FastAPI",
                "version": match.group(1),
                "language": "Python",
                "has_backend": True
            }
        if match := re.search(r"flask[>=<~]=*([\d.]+)", content, re.I):
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
