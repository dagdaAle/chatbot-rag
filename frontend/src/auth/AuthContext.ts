import { createContext, useContext } from 'react';
import type { User } from '@supabase/supabase-js';
import type { Profile } from '@/api/admin';

export interface AuthState {
  user: User;
  profile: Profile;
}

export const AuthContext = createContext<AuthState | null>(null);

function useAuth() {
  const state = useContext(AuthContext);
  if (!state) throw new Error('Sessione richiesta');
  return state;
}

export const useAuthUser = () => useAuth().user;

/** Profilo applicativo letto dal server: è la sola fonte del ruolo nel frontend. */
export function useProfile() {
  const { profile } = useAuth();
  return {
    profile,
    isAdmin: profile.role === 'admin',
    canCreateKnowledge: profile.role === 'admin' || profile.role === 'member',
  };
}
