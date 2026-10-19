export let constructed = 0;
export let dropped = 0;
export function transform(value) {
  if (value.text === 'fail') throw 'host-error';
  return { text: value.text + ' ✓', bytes: new Uint8Array([...value.bytes].reverse()) };
}
export class Iterator {
  constructor(data) { this.data = data; this.index = 0; constructed++; }
  next() { return this.index < this.data.length ? this.data[this.index++] : undefined; }
  [Symbol.dispose]() { dropped++; }
}
