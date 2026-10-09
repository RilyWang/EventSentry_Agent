import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { trpc } from "../providers/trpc";

export function useAuth() {
  const queryClient = useQueryClient();

  const { data: user, isLoading } = trpc.auth.me.useQuery(undefined, {
    retry: false,
    refetchOnWindowFocus: false,
  });

  const logout = trpc.auth.logout.useMutation({
    onSuccess: () => {
      queryClient.invalidateQueries();
      window.location.reload();
    },
  });

  return {
    user,
    isLoading,
    isLoggedIn: !!user,
    logout: logout.mutate,
  };
}
