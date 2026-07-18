# QuickEdit

QuickEdit is a local-first video editing CLI. It removes silence and inactive
sections using speech and motion analysis, then can generate animated or SRT
subtitles. Optional semantic cuts use an LLM only when you explicitly enable
them.

## Install

QuickEdit requires Python 3.11+, FFmpeg, and FFprobe.

```bash
pip install quickedit
quickedit myvideo.mp4 --dry-run
```

Enable semantic LLM editing only when you are ready to send transcript data to
your selected provider:

```bash
pip install 'quickedit[anthropic]'
export ANTHROPIC_API_KEY='...'
quickedit myvideo.mp4 --llm
```

## Documentation and support

- [Documentation](https://idityaGE.github.io/quick-edit/)
- [Report a bug](https://github.com/idityaGE/quick-edit/issues/new/choose)
- [Ask a question or share an idea](https://github.com/idityaGE/quick-edit/discussions)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

[MIT](LICENSE)
