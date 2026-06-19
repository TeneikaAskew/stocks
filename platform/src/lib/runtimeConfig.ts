/**
 * Runtime auth config, fetched once at boot from GET /api/config/firebase.
 * Lets one built image serve any environment (the Firebase web config + auth
 * mode come from server env, not a build-time bake).
 */
export interface FirebaseWebConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
}

export type AuthMode = 'firebase' | 'iap' | 'open';

export interface RuntimeConfig {
  authMode: AuthMode;
  firebase: FirebaseWebConfig | null;
}

let _config: RuntimeConfig = { authMode: 'open', firebase: null };

export function setRuntimeConfig(c: RuntimeConfig): void {
  _config = c;
}

export function getRuntimeConfig(): RuntimeConfig {
  return _config;
}

export function getAuthMode(): AuthMode {
  return _config.authMode;
}
