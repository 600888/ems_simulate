import type { IEC61850DoNode } from '@/api/channelApi'

const PRIMARY_DA_PATHS: Record<number, string[]> = {
  0: ['mag.f', 'mag.i', 'cVal.f', 'cVal.i', 'instMag.f', 'instMag.i', 'mxVal.f', 'mxVal.i', 'mag'],
  1: ['stVal'],
  2: ['ctlVal', 'Oper.ctlVal', 'SBOw.ctlVal'],
  3: ['setVal.f', 'setVal.i', 'setVal', 'ctlVal', 'Oper.ctlVal', 'SBOw.ctlVal'],
}

const NON_VALUE_DA_NAMES = new Set(['q', 't', 'dU'])
const CONTROL_DA_PATHS = ['Oper.ctlVal', 'SBOw.ctlVal', 'ctlVal']

export function isControlValuePointCode(pointCode: string): boolean {
  return CONTROL_DA_PATHS.some(path => pointCode === path || pointCode.endsWith(`.${path}`))
}

/** Control objects use IEC 61850 control services and are not directly readable. */
export function isControlObject(doNode: IEC61850DoNode): boolean {
  return (doNode.children || []).some(da =>
    da.fc === 'CO' || (da.children || []).some(bda => bda.fc === 'CO')
  )
}

/** Resolve the FC=CO point used to operate a control object. */
export function resolveDoControlPointCode(doNode: IEC61850DoNode): string {
  const candidates: Array<{ path: string; code: string; fc: string }> = []

  for (const da of doNode.children || []) {
    if (da.point_code) {
      candidates.push({ path: da.da_path, code: da.point_code, fc: da.fc })
    }
    for (const bda of da.children || []) {
      if (bda.point_code) {
        candidates.push({ path: bda.bda_path, code: bda.point_code, fc: bda.fc })
      }
    }
  }

  for (const preferredPath of CONTROL_DA_PATHS) {
    const match = candidates.find(candidate =>
      candidate.fc === 'CO'
      && (candidate.path === preferredPath || candidate.code.endsWith(`.${preferredPath}`))
    )
    if (match) return match.code
  }
  return ''
}

/**
 * Resolve the actual registered point behind a DO-level read button.
 *
 * Online models may expose values as mag.i, Oper.ctlVal, or another device-
 * specific DA/BDA. Prefer the point codes returned by the backend instead of
 * assuming every DO uses mag.f/stVal/ctlVal.
 */
export function resolveDoReadPointCode(doNode: IEC61850DoNode): string {
  const candidates: Array<{ path: string; code: string }> = []

  for (const da of doNode.children || []) {
    if (da.point_code) {
      candidates.push({ path: da.da_path, code: da.point_code })
    }
    for (const bda of da.children || []) {
      if (bda.point_code) {
        candidates.push({ path: bda.bda_path, code: bda.point_code })
      }
    }
  }

  for (const preferredPath of PRIMARY_DA_PATHS[doNode.frame_type] || []) {
    const match = candidates.find(candidate => candidate.path === preferredPath)
    if (match) return match.code
  }

  const firstValuePoint = candidates.find(candidate => {
    const topLevelName = candidate.path.split('.')[0]
    return !NON_VALUE_DA_NAMES.has(topLevelName)
  })
  if (firstValuePoint) return firstValuePoint.code

  // Keep the legacy fallback for models that have a known frame type but have
  // not supplied point_code yet (for example while the tree is refreshing).
  const fallbackPath: Record<number, string> = {
    0: 'mag.f',
    1: 'stVal',
    2: 'ctlVal',
    3: 'ctlVal',
  }
  const path = fallbackPath[doNode.frame_type]
  return path ? `${doNode.do_ref}.${path}` : ''
}
