const PREFIX = "[misi-bayang-ui]";

function stamp(): string {
  return new Date().toISOString();
}

function withMeta(scope: string, message: string): string {
  return `${PREFIX} ${stamp()} [${scope}] ${message}`;
}

export function logInfo(scope: string, message: string, payload?: unknown): void {
  if (payload === undefined) {
    console.log(withMeta(scope, message));
    return;
  }
  console.log(withMeta(scope, message), payload);
}

export function logWarn(scope: string, message: string, payload?: unknown): void {
  if (payload === undefined) {
    console.warn(withMeta(scope, message));
    return;
  }
  console.warn(withMeta(scope, message), payload);
}

export function logError(scope: string, message: string, payload?: unknown): void {
  if (payload === undefined) {
    console.error(withMeta(scope, message));
    return;
  }
  console.error(withMeta(scope, message), payload);
}

export function logDebug(scope: string, message: string, payload?: unknown): void {
  if (payload === undefined) {
    console.debug(withMeta(scope, message));
    return;
  }
  console.debug(withMeta(scope, message), payload);
}
