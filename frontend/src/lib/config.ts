/**
 * Runtime config. In the container, /config.js sets window.__CONFIG__ from Cloud Run env
 * vars, so the same image runs anywhere. In local dev that object is empty and the Vite
 * env (.env) fills in.
 */
type RuntimeConfig = Partial<{
  API_URL: string;
  CAFE_ID: string;
  FIREBASE_API_KEY: string;
  FIREBASE_AUTH_DOMAIN: string;
  FIREBASE_PROJECT_ID: string;
  FIREBASE_STORAGE_BUCKET: string;
  FIREBASE_MESSAGING_SENDER_ID: string;
  FIREBASE_APP_ID: string;
}>;

declare global {
  interface Window {
    __CONFIG__?: RuntimeConfig;
  }
}

const rt: RuntimeConfig = window.__CONFIG__ ?? {};
const env = import.meta.env;

export const config = {
  apiUrl: (rt.API_URL || env.VITE_API_URL || 'http://localhost:8080').replace(/\/$/, ''),
  cafeId: rt.CAFE_ID || env.VITE_CAFE_ID || 'koramangala',
  firebase: {
    apiKey: rt.FIREBASE_API_KEY || env.VITE_FIREBASE_API_KEY,
    authDomain: rt.FIREBASE_AUTH_DOMAIN || env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: rt.FIREBASE_PROJECT_ID || env.VITE_FIREBASE_PROJECT_ID,
    storageBucket: rt.FIREBASE_STORAGE_BUCKET || env.VITE_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: rt.FIREBASE_MESSAGING_SENDER_ID || env.VITE_FIREBASE_MESSAGING_SENDER_ID,
    appId: rt.FIREBASE_APP_ID || env.VITE_FIREBASE_APP_ID,
  },
};
