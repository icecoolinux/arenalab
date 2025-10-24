/** @type {import('next').NextConfig} */
const nextConfig = {
	images: { unoptimized: true },
	experimental: {
		// Increase body size limit for file uploads (1GB)
		serverActions: {
			bodySizeLimit: '1gb'
		}
	},
	// Configure API proxy for internal container communication
	async rewrites() {
		return [
			{
				source: '/api/:path*',
				destination: 'http://127.0.0.1:8000/api/:path*'
			},
			// TensorBoard proxy - handle directory path properly
			{
				source: '/tb/:path*',
				destination: 'http://localhost:8000/tb/:path*'
			},
			{
				source: '/tb/',
				destination: 'http://localhost:8000/tb/'
			},
			{
				source: '/tb',
				destination: 'http://localhost:8000/tb/'
			},
			// TensorBoard static assets - proxy root-level assets when they're TensorBoard requests
			{
				source: '/index.js',
				destination: 'http://localhost:8000/tb/index.js',
				has: [
					{
						type: 'header',
						key: 'referer',
						value: '.*/tb.*'
					}
				]
			},
			{
				source: '/chart_worker.js',
				destination: 'http://localhost:8000/tb/chart_worker.js'
			},
			{
				source: '/font-roboto/:path*',
				destination: 'http://localhost:8000/tb/font-roboto/:path*'
			},
			// TensorBoard data API endpoints - these are TensorBoard-specific so always proxy
			{
				source: '/data/:path*',
				destination: 'http://localhost:8000/tb/data/:path*'
			},
			{
				source: '/experiment/:path*',
				destination: 'http://localhost:8000/tb/experiment/:path*'
			},
			// TensorBoard additional static assets
			{
				source: '/icon_bundle.svg',
				destination: 'http://localhost:8000/tb/icon_bundle.svg',
				has: [
					{
						type: 'header',
						key: 'referer',
						value: '.*/tb.*'
					}
				]
			}
		];
	}
};

export default nextConfig;
