import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyAami7n01CmBp1EvwMaCzNSXsjlt5XvAoE",
  authDomain: "medlive-488722.firebaseapp.com",
  projectId: "medlive-488722",
  storageBucket: "medlive-488722.firebasestorage.app",
  messagingSenderId: "479757625763",
  appId: "1:479757625763:web:61c5299bf510e2b3c3d216",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export default app;
