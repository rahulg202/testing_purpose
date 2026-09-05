import { createContext, useContext, ReactNode } from 'react';

// DEV MODE: Auth bypassed for local development without Cognito.
// TODO: Restore real Cognito auth before pilot deployment.

interface User {
  userId: string;
  email: string;
  givenName?: string;
  familyName?: string;
  tenantId?: string;
  role?: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  getAccessToken: () => Promise<string | null>;
}

const DEV_USER: User = {
  userId: 'dev-user-001',
  email: 'dev@atheria.local',
  givenName: 'Dev',
  familyName: 'User',
  tenantId: 'acme_pharma',
  role: 'reviewer',
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Bypassed: always authenticated with a dev user
  const user = DEV_USER;
  const isLoading = false;

  async function login(_email: string, _password: string) {
    // No-op in dev mode
  }

  async function logout() {
    // No-op in dev mode
  }

  async function getAccessToken(): Promise<string | null> {
    return 'dev-token';
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: true,
        isLoading,
        login,
        logout,
        getAccessToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
