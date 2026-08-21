import { NextRequest, NextResponse } from "next/server";

/**
 * Rol bazlı rota koruması. Oturum yoksa /login'e yönlendirir.
 * (Gerçek yetki kontrolü backend JWT + rol dependency'lerinde yapılır.)
 */
export function middleware(request: NextRequest) {
  const authed = request.cookies.has("pulsar_auth");
  const { pathname } = request.nextUrl;

  const protectedPaths = ["/dashboard", "/viewer", "/approvals", "/studies"];
  if (!authed && protectedPaths.some((p) => pathname.startsWith(p))) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  if (authed && pathname === "/login") {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/viewer/:path*", "/approvals/:path*", "/studies/:path*", "/login"],
};
