import { useEffect, useRef } from 'react'

// A modal window's keyboard: the focus starts on its ✕ (startRef), Tab and Shift+Tab go round inside
// it (boxRef), and Esc closes it. The parent gives the focus back to the opener when it closes.
// A radio group is one stop for Tab (the checked option), as the browser does.
export function useModalFocus(boxRef, startRef, onClose) {
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose }, [onClose])
  useEffect(() => {
    startRef.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); onCloseRef.current(); return }
      if (e.key !== 'Tab' || !boxRef.current) return
      const items = [...boxRef.current.querySelectorAll('button, input, select, a[href]')]
        .filter((el) => !el.disabled && !(el.type === 'radio' && !el.checked))
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      const inside = boxRef.current.contains(document.activeElement)
      if (e.shiftKey && (document.activeElement === first || !inside)) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && (document.activeElement === last || !inside)) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}

// a click on the dark area outside closes it - on the click itself, so the browser's own focus change
// comes first, and only if it started outside too (a selection dragged out of a field does not close it)
export function useOutsideClick(onClose) {
  const downOutside = useRef(false)
  return {
    onMouseDown: (e) => { downOutside.current = e.target === e.currentTarget },
    onClick: (e) => { if (downOutside.current && e.target === e.currentTarget) onClose() },
  }
}
