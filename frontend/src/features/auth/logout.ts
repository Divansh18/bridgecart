import { ApiError } from "@/lib/api";

type LogoutOutcome =
  { confirmed: true } | { confirmed: false; message: string };

export async function attemptLogout(
  request: () => Promise<unknown>,
): Promise<LogoutOutcome> {
  try {
    await request();
    return { confirmed: true };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401)
      return { confirmed: true };
    return {
      confirmed: false,
      message: "Could not sign out. Your session may still be active. Retry.",
    };
  }
}
