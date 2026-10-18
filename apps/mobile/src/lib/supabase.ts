// The session of the anonymous player is kept by expo-sqlite's localStorage.
import 'expo-sqlite/localStorage/install';

import { type SupabaseClient, createClient } from '@supabase/supabase-js';

// The project and its public key come from the environment of the build
// (apps/mobile/.env, out of git; see .env.example). The key is not a secret:
// the rules of the database decide what a player may do.
const URL = process.env.EXPO_PUBLIC_SUPABASE_URL;
const KEY = process.env.EXPO_PUBLIC_SUPABASE_KEY;

/** The server of Lutèce; none in a build made without its address. */
export const supabase: SupabaseClient | null =
  URL && KEY
    ? createClient(URL, KEY, {
        auth: {
          storage: localStorage,
          autoRefreshToken: true,
          persistSession: true,
          detectSessionInUrl: false,
        },
      })
    : null;
