"use client"

import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"

interface AnimatedTextProps {
  words: string[]
  className?: string
}

export function AnimatedText({ words, className }: AnimatedTextProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isAnimating, setIsAnimating] = useState(false)

  useEffect(() => {
    const interval = setInterval(() => {
      setIsAnimating(true)
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % words.length)
        setIsAnimating(false)
      }, 300)
    }, 3000)

    return () => clearInterval(interval)
  }, [words.length])

  return (
    <span
      className={cn(
        "inline-block transition-all duration-300",
        isAnimating ? "opacity-0 translate-y-2" : "opacity-100 translate-y-0",
        className
      )}
    >
      {words[currentIndex]}
    </span>
  )
}

interface GlitchTextProps {
  text: string
  className?: string
}

export function GlitchText({ text, className }: GlitchTextProps) {
  const [displayText, setDisplayText] = useState(text)
  const [isGlitching, setIsGlitching] = useState(false)

  useEffect(() => {
    const chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    let timeout: NodeJS.Timeout

    const glitch = () => {
      if (Math.random() > 0.97) {
        setIsGlitching(true)
        let iterations = 0
        const maxIterations = 3

        const interval = setInterval(() => {
          setDisplayText(
            text
              .split("")
              .map((char, i) => {
                if (i < iterations) return text[i]
                if (char === " ") return " "
                return Math.random() > 0.5 ? chars[Math.floor(Math.random() * chars.length)] : char
              })
              .join("")
          )
          iterations++
          if (iterations > text.length + maxIterations) {
            clearInterval(interval)
            setDisplayText(text)
            setIsGlitching(false)
          }
        }, 30)
      }
      timeout = setTimeout(glitch, 100)
    }

    glitch()
    return () => clearTimeout(timeout)
  }, [text])

  return (
    <span
      className={cn(
        "inline-block transition-colors",
        isGlitching && "text-primary",
        className
      )}
    >
      {displayText}
    </span>
  )
}
