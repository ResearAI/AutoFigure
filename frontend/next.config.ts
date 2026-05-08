import type { NextConfig } from "next"

const nextConfig: NextConfig = {
    /* config options here */
    // Next.js may emit traced chunk filenames containing ":" for standalone output.
    // Those filenames are invalid on native Windows, so keep standalone packaging for
    // non-Windows environments and use the normal build output on Windows.
    output: process.platform === "win32" ? undefined : "standalone",

    async rewrites() {
        return [
            {
                source: "/backend/:path*",
                destination: "http://127.0.0.1:8796/:path*",
            },
        ]
    },

    // Increase body size limit for Server Actions and API routes (for PDF uploads)
    experimental: {
        serverActions: {
            bodySizeLimit: "50mb",
        },
    },
}

export default nextConfig
