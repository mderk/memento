import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync } from "node:fs";
import { basename, dirname, extname, join, relative, resolve } from "node:path";

export interface ProtocolCandidate {
	protocolDir: string;
	label: string;
	score: number;
}

export interface CreateProtocolInput {
	protocolDir: string;
	protocolDirDisplay: string;
	prdSource: string;
	copiedPrdFrom?: string;
}

export function toWorkflowPath(path: string, cwd: string): string {
	const rel = relative(cwd, path);
	if (rel && !rel.startsWith("..") && rel !== ".") return rel.replace(/\\/g, "/");
	return path;
}

export function listProtocolCandidates(cwd: string): ProtocolCandidate[] {
	return listProtocolDirs(cwd).map((protocolDir) => ({
		protocolDir,
		label: toWorkflowPath(protocolDir, cwd),
		score: 0,
	}));
}

export function findProtocolCandidates(arg: string, cwd: string): ProtocolCandidate[] {
	const trimmed = arg.trim();
	if (!trimmed) return listProtocolCandidates(cwd);

	const pathCandidate = resolvePathCandidate(trimmed, cwd);
	if (pathCandidate) return [pathCandidate];

	if (/^\d+$/.test(trimmed)) return findByProtocolNumber(trimmed, cwd);
	return findByDescription(trimmed, cwd);
}

export function ensurePlanExists(protocolDir: string): void {
	const planPath = join(protocolDir, "plan.md");
	if (!existsSync(planPath)) throw new Error(`protocol has no plan.md: ${protocolDir}`);
}

export function readLastRun(protocolDir: string): string | null {
	const path = join(protocolDir, ".last_run");
	if (!existsSync(path)) return null;
	const runId = readFileSync(path, "utf-8").trim();
	return runId || null;
}

export function prepareCreateProtocol(rawArgs: string, cwd: string): CreateProtocolInput {
	const trimmed = rawArgs.trim();
	if (!trimmed) throw new Error("usage: /mw create-protocol <protocol number | protocol path | prd.md path | task description>");

	const numbered = trimmed.match(/^(\d+)\s+(.+)$/);
	if (numbered) {
		const protocolNumber = Number.parseInt(numbered[1] ?? "", 10);
		const description = (numbered[2] ?? "").trim();
		const existing = findByProtocolNumber(numbered[1] ?? "", cwd);
		if (existing.length > 0) {
			const protocolDir = existing[0]!.protocolDir;
			if (!hasPrd(protocolDir) && !hasPlanJson(protocolDir) && description) {
				return {
					protocolDir,
					protocolDirDisplay: toWorkflowPath(protocolDir, cwd),
					prdSource: description,
				};
			}
			assertCreateInputsAvailable(protocolDir);
			return {
				protocolDir,
				protocolDirDisplay: toWorkflowPath(protocolDir, cwd),
				prdSource: hasPrd(protocolDir) ? "" : description,
			};
		}
		const protocolDir = createProtocolDir(cwd, protocolNumber, description);
		return {
			protocolDir,
			protocolDirDisplay: toWorkflowPath(protocolDir, cwd),
			prdSource: description,
		};
	}

	const pathCandidate = resolvePathCandidate(trimmed, cwd);
	if (pathCandidate) {
		const resolved = pathCandidate.protocolDir;
		const inputPath = resolve(cwd, trimmed);
		if (existsSync(inputPath) && extname(inputPath).toLowerCase() === ".md" && basename(inputPath).toLowerCase() !== "plan.md") {
			if (
				basename(inputPath).toLowerCase() === "prd.md"
				&& existsSync(join(resolved, "prd.md"))
				&& isUnderProtocolRoot(resolved, cwd)
			) {
				return {
					protocolDir: resolved,
					protocolDirDisplay: toWorkflowPath(resolved, cwd),
					prdSource: "",
				};
			}
			const protocolDir = createProtocolDir(cwd, nextProtocolNumber(cwd), basename(inputPath, extname(inputPath)));
			copyPrdFile(inputPath, protocolDir);
			return {
				protocolDir,
				protocolDirDisplay: toWorkflowPath(protocolDir, cwd),
				prdSource: "",
				copiedPrdFrom: inputPath,
			};
		}

		assertCreateInputsAvailable(resolved);
		return {
			protocolDir: resolved,
			protocolDirDisplay: toWorkflowPath(resolved, cwd),
			prdSource: "",
		};
	}

	const protocolDir = createProtocolDir(cwd, nextProtocolNumber(cwd), trimmed);
	return {
		protocolDir,
		protocolDirDisplay: toWorkflowPath(protocolDir, cwd),
		prdSource: trimmed,
	};
}

function protocolRoot(cwd: string): string {
	return join(cwd, ".protocols");
}

function listProtocolDirs(cwd: string): string[] {
	const root = protocolRoot(cwd);
	if (!existsSync(root)) return [];
	return readdirSync(root, { withFileTypes: true })
		.filter((entry) => entry.isDirectory())
		.map((entry) => join(root, entry.name))
		.sort();
}

function findByProtocolNumber(arg: string, cwd: string): ProtocolCandidate[] {
	const target = Number.parseInt(arg, 10);
	if (!Number.isFinite(target)) return [];
	return listProtocolDirs(cwd)
		.map((protocolDir) => ({
			protocolDir,
			label: toWorkflowPath(protocolDir, cwd),
			match: basename(protocolDir).match(/^(\d+)/),
		}))
		.filter((candidate) => candidate.match && Number.parseInt(candidate.match[1] ?? "", 10) === target)
		.map((candidate) => ({
			protocolDir: candidate.protocolDir,
			label: candidate.label,
			score: 100,
		}));
}

function resolvePathCandidate(arg: string, cwd: string): ProtocolCandidate | null {
	const inputPath = resolve(cwd, arg);
	if (!existsSync(inputPath)) return null;
	const protocolDir = extname(inputPath).toLowerCase() === ".md" ? dirname(inputPath) : inputPath;
	return {
		protocolDir,
		label: toWorkflowPath(protocolDir, cwd),
		score: 1000,
	};
}

function findByDescription(query: string, cwd: string): ProtocolCandidate[] {
	const normalizedQuery = normalize(query);
	const tokens = normalizedQuery.split(/\s+/).filter(Boolean);
	return listProtocolDirs(cwd)
		.map((protocolDir) => {
			const haystack = [
				normalize(basename(protocolDir)),
				readNormalized(join(protocolDir, "plan.md")),
				readNormalized(join(protocolDir, "prd.md")),
			].join("\n");
			let score = 0;
			if (normalize(basename(protocolDir)).includes(normalizedQuery)) score += 100;
			if (haystack.includes(normalizedQuery)) score += 50;
			if (tokens.length > 0 && tokens.every((token) => haystack.includes(token))) score += tokens.length;
			return {
				protocolDir,
				label: toWorkflowPath(protocolDir, cwd),
				score,
			};
		})
		.filter((candidate) => candidate.score > 0)
		.sort((a, b) => b.score - a.score || a.label.localeCompare(b.label));
}

function normalize(value: string): string {
	return value.toLowerCase();
}

function readNormalized(path: string): string {
	if (!existsSync(path)) return "";
	try {
		return normalize(readFileSync(path, "utf-8"));
	} catch {
		return "";
	}
}

function nextProtocolNumber(cwd: string): number {
	let maxNumber = 0;
	for (const protocolDir of listProtocolDirs(cwd)) {
		const match = basename(protocolDir).match(/^(\d+)/);
		if (!match) continue;
		const value = Number.parseInt(match[1] ?? "", 10);
		if (Number.isFinite(value)) maxNumber = Math.max(maxNumber, value);
	}
	return maxNumber + 1;
}

function createProtocolDir(cwd: string, number: number, description: string): string {
	const dir = join(protocolRoot(cwd), `${String(number).padStart(4, "0")}-${slugify(description)}`);
	mkdirSync(dir, { recursive: true });
	return dir;
}

function slugify(value: string): string {
	const slug = value
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/^-+|-+$/g, "")
		.slice(0, 48);
	return slug || "protocol";
}

function copyPrdFile(sourcePath: string, protocolDir: string): void {
	mkdirSync(protocolDir, { recursive: true });
	copyFileSync(sourcePath, join(protocolDir, "prd.md"));
}

function isUnderProtocolRoot(path: string, cwd: string): boolean {
	const rel = relative(protocolRoot(cwd), path);
	return rel === "" || (!rel.startsWith("..") && rel !== ".");
}

function hasPrd(protocolDir: string): boolean {
	return existsSync(join(protocolDir, "prd.md"));
}

function hasPlanJson(protocolDir: string): boolean {
	return existsSync(join(protocolDir, "plan.json"));
}

function assertCreateInputsAvailable(protocolDir: string): void {
	if (!hasPrd(protocolDir) && !hasPlanJson(protocolDir)) {
		throw new Error(`protocol dir must contain prd.md or plan.json: ${protocolDir}`);
	}
}
