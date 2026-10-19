import { z } from "zod";

export const signInSchema = z.object({
  email: z.email(),
  password: z.string().min(1),
});

export const signUpSchema = z.object({
  email: z.email(),
  password: z.string().min(8),
});

export const createCandidateSchema = z.object({
  name: z.string().trim().min(1),
  email: z.email(),
  role_id: z.number().int().positive(),
});

export const overrideScoreSchema = z.object({
  final_score: z.number().int().min(1).max(4),
  override_reason: z.string().trim().min(1),
});

export type SignInInput = z.infer<typeof signInSchema>;
export type SignUpInput = z.infer<typeof signUpSchema>;
export type CreateCandidateInput = z.infer<typeof createCandidateSchema>;
export type OverrideScoreInput = z.infer<typeof overrideScoreSchema>;
