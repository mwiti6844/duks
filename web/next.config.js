/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // API_INTERNAL_URL is read server-side at runtime only (the BFF proxy + auth
  // routes). It is intentionally NOT exposed to the browser and not needed at build.
};

module.exports = nextConfig;
