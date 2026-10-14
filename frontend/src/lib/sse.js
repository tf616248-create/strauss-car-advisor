// Incremental parser for text/event-stream. Feed it decoded text chunks.
export function createSSEParser(onEvent) {
  let buffer = ''
  return {
    feed(text) {
      buffer += text.replace(/\r\n/g, '\n')
      let end
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, end)
        buffer = buffer.slice(end + 2)
        let event = 'message'
        const data = []
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
        }
        if (data.length) onEvent(event, JSON.parse(data.join('\n')))
      }
    },
  }
}
