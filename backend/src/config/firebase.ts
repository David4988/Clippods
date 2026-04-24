import * as admin from 'firebase-admin';

export function initFirebase() {
  if (!admin.apps.length) {
    try {
      // It expects GOOGLE_APPLICATION_CREDENTIALS in env locally
      admin.initializeApp({
        credential: admin.credential.applicationDefault()
      });
      console.log('[startup] ✅ Firebase Admin initialized.');
    } catch (error) {
      console.error('[startup] ❌ Firebase Admin initialization failed:', error);
    }
  }
}

export const firebaseAdmin = admin;
