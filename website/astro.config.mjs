import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://idityaGE.github.io',
  base: '/quick-edit',
  integrations: [
    starlight({
      title: 'QuickEdit',
      description: 'Local-first AI-assisted video editing from the command line.',
      social: [{
        icon: 'github',
        label: 'GitHub',
        href: 'https://github.com/idityaGE/quick-edit',
      }],
      editLink: {
        baseUrl: 'https://github.com/idityaGE/quick-edit/edit/main/website/',
      },
      sidebar: [
        { label: 'Start here', items: [
          { label: 'Overview', slug: 'index' },
          { label: 'Install QuickEdit', slug: 'getting-started/install' },
          { label: 'Your first edit', slug: 'getting-started/first-edit' },
        ] },
        { label: 'Guides', items: [
          { label: 'Common commands', slug: 'guides/common-commands' },
          { label: 'Editing controls', slug: 'guides/editing-controls' },
          { label: 'Subtitles, output, and cache', slug: 'guides/output-and-cache' },
          { label: 'Optional LLM editing', slug: 'guides/llm-editing' },
          { label: 'How it works', slug: 'guides/how-it-works' },
          { label: 'Motion benchmarks', slug: 'guides/motion-benchmarks' },
          { label: 'Troubleshooting', slug: 'guides/troubleshooting' },
        ] },
        { label: 'Reference', items: [
          { label: 'CLI reference', slug: 'reference/cli' },
          { label: 'Timeline JSON', slug: 'reference/timeline-json' },
        ] },
        { label: 'Project', items: [
          { label: 'Contributing', slug: 'project/contributing' },
          { label: 'Security and privacy', slug: 'project/security-and-privacy' },
        ] },
      ],
    }),
  ],
});
