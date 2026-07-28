import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/apiClient";
import type { Conversation } from "@/types";

const conversationsKey = ["conversations"] as const;

async function fetchConversations(): Promise<Conversation[]> {
  const { data } = await apiClient.get<Conversation[]>("/conversations");
  return data;
}

/** The signed-in user's conversation history (drives StatsCard + HistoryCard). */
export function useConversations() {
  return useQuery({ queryKey: conversationsKey, queryFn: fetchConversations });
}

async function deleteConversation(id: string): Promise<void> {
  await apiClient.delete(`/conversations/${id}`);
}

/** Delete a conversation, then refresh the history list. */
export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: conversationsKey }),
  });
}
