import { getApp, getApps, initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';
import { config } from './config';

// Reuse the app across Vite hot reloads (initializeApp twice throws duplicate-app).
export const app = getApps().length ? getApp() : initializeApp(config.firebase);
export const auth = getAuth(app);

/**
 * Read-only realtime listeners (order tracker, barista board, live wait, Connect chat).
 * Every write goes through the API; firestore.rules deny client writes.
 */
export const firestore = getFirestore(app, 'cafedata');
