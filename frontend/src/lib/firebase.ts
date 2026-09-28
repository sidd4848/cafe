import { getApp, getApps, initializeApp } from 'firebase/app';
import { connectAuthEmulator, getAuth } from 'firebase/auth';
import { connectFirestoreEmulator, getFirestore } from 'firebase/firestore';
import { config } from './config';

// Reuse the app across Vite hot reloads (initializeApp twice throws duplicate-app).
export const app = getApps().length ? getApp() : initializeApp(config.firebase);
export const auth = getAuth(app);

// Local testing only: point Auth at the Firebase emulator (never set in the deployed image).
if (import.meta.env.VITE_AUTH_EMULATOR) {
  connectAuthEmulator(auth, import.meta.env.VITE_AUTH_EMULATOR, { disableWarnings: true });
}

/**
 * Read-only realtime listeners (order tracker, barista board, live wait, Connect chat).
 * Every write goes through the API; firestore.rules deny client writes.
 */
export const firestore = getFirestore(app, 'cafedata');

// Local testing only: Firestore emulator as "host:port" (never set in the deployed image).
if (import.meta.env.VITE_FIRESTORE_EMULATOR) {
  const [host, port] = String(import.meta.env.VITE_FIRESTORE_EMULATOR).split(':');
  connectFirestoreEmulator(firestore, host, Number(port));
}
