export {}

declare global {
  function __(text: string, replace?: unknown, context?: string | null): string

  interface String {
    format(...args: any[]): string
  }
}

declare module 'vue' {
  interface ComponentCustomProperties {
    __: (text: string, replace?: unknown, context?: string | null) => string
  }
}