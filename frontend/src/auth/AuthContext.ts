import { createContext, useContext } from 'react';
import type { User } from '@supabase/supabase-js';

export const AuthContext = createContext<User | null>(null);
export function useAuthUser() {
  const user = useContext(AuthContext);
  if (!user) throw new Error('Sessione richiesta');
  return user;
}
