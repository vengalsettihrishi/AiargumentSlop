export async function* fetchDebateStream(query: string) {
  const response = await fetch('http://127.0.0.1:8000/api/debate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    throw new Error(`Failed to start debate: ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  if (!reader) return;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep the incomplete line in the buffer

      let currentEvent = '';

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.substring(7).trim();
        } else if (line.startsWith('data: ')) {
          const dataStr = line.substring(6).trim();
          if (dataStr) {
            try {
              const data = JSON.parse(dataStr);
              yield { event: currentEvent, data };
            } catch (e) {
              console.error('Failed to parse SSE data', dataStr);
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
