import { sessionGet, sessionLogin, sessionLogout } from "@/auth/server/session";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const GET = sessionGet;
export const POST = sessionLogin;
export const DELETE = sessionLogout;
