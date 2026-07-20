import type { ReactNode } from 'react'
import type { OnboardingStep } from '../../types'

const STEP_ORDER: OnboardingStep[] = ['welcome', 'aws']

interface OnboardingLayoutProps {
  step: OnboardingStep
  children: ReactNode
}

export function OnboardingLayout({ step, children }: OnboardingLayoutProps) {
  const stepIndex = STEP_ORDER.indexOf(step)
  return (
    <div className="onboarding">
      <div className="onboarding__inner">
        <div className="progress-dots">
          {STEP_ORDER.map((s, i) => (
            <div
              key={s}
              className={[
                'progress-dot',
                i <= stepIndex ? 'progress-dot--reached' : '',
                i === stepIndex ? 'progress-dot--current' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            />
          ))}
        </div>
        {children}
      </div>
    </div>
  )
}
