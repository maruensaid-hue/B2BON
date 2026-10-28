import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// Cabeçalhos de segurança do site publicado (auditoria A05). O Cloudflare serve os arquivos estáticos direto, sem passar pelo worker.js (só /api/* passa), e
// lê as regras do arquivo `_headers` da pasta publicada. Este plugin o gera ao fim de cada build, porque a CSP precisa do hash de cada <script> inline do index.html:
// assim nenhum script inline é liberado em bloco (nada de 'unsafe-inline' em script-src) e o hash acompanha qualquer edição desses scripts.
function cabecalhosDeSeguranca(): Plugin {
  let pastaPublicada = ''
  return {
    name: 'b2bon-cabecalhos-de-seguranca',
    apply: 'build',
    configResolved(config) {
      pastaPublicada = resolve(config.root, config.build.outDir)
    },
    closeBundle() {
      const fonte = readFileSync(resolve(pastaPublicada, 'index.html'), 'utf8')
      // O navegador normaliza as quebras de linha para LF antes de calcular o hash de um script inline; o arquivo pode estar em CRLF.
      const normalizar = (texto: string) => texto.split('\r\n').join('\n').split('\r').join('\n')
      const hashes = [...fonte.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(
        (m) => `'sha256-${createHash('sha256').update(normalizar(m[1]), 'utf8').digest('base64')}'`,
      )
      const csp = [
        "default-src 'self'",
        `script-src 'self' https://accounts.google.com ${hashes.join(' ')}`.trim(),
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com",
        "font-src 'self' data: https://fonts.gstatic.com",
        // logos e imagens de perfil/post são endereços colados pelos usuários (qualquer https); mídia própria vem de /api
        "img-src 'self' data: blob: https:",
        "media-src 'self' blob: data:",
        "connect-src 'self' https://accounts.google.com",
        'frame-src https://accounts.google.com',
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
        "worker-src 'self'",
        "manifest-src 'self'",
      ].join('; ')
      const regras = [
        `Content-Security-Policy: ${csp}`,
        'X-Content-Type-Options: nosniff',
        'X-Frame-Options: DENY',
        'Referrer-Policy: strict-origin-when-cross-origin',
        'Strict-Transport-Security: max-age=31536000',
        'Permissions-Policy: camera=(), microphone=(), geolocation=()',
      ]
      const source = ['/*', ...regras.map((r) => `  ${r}`), ''].join('\n')
      writeFileSync(resolve(pastaPublicada, '_headers'), source)
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    cabecalhosDeSeguranca(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'B2B ON — Operating Network',
        short_name: 'B2B ON',
        description: 'Núcleo B2B ON — CRM, Rede Social, MAP e PREDATOR integrados.',
        theme_color: '#050D1A',
        background_color: '#050D1A',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
