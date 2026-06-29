/// <reference types="jest" />

import type { IEC61850DoNode } from '@/api/channelApi'
import { resolveDoReadPointCode } from '@/utils/iec61850Tree'

function makeDo(overrides: Partial<IEC61850DoNode>): IEC61850DoNode {
  return {
    do_name: 'Value1',
    do_ref: 'LD0/GGIO1.Value1',
    ld: 'LD0',
    ln: 'GGIO1',
    du_name: '',
    fc: 'MX',
    frame_type: -1,
    children: [],
    ...overrides,
  }
}

function makeDa(path: string, pointCode = '', children: any[] = []) {
  return {
    da_name: path.split('.')[0],
    da_path: path,
    fc: 'MX',
    is_struct: children.length > 0,
    point_code: pointCode,
    point_name: path,
    value: '',
    status: '',
    children,
  }
}

describe('resolveDoReadPointCode', () => {
  it('uses the actual integer magnitude BDA instead of hard-coded mag.f', () => {
    const node = makeDo({
      frame_type: 0,
      children: [makeDa('mag', '', [
        { bda_name: 'i', bda_path: 'mag.i', fc: 'MX', point_code: 'MMXU1.Value1.mag.i', value: '', status: '' },
      ])],
    })

    expect(resolveDoReadPointCode(node)).toBe('MMXU1.Value1.mag.i')
  })

  it('uses nested control values returned by the model', () => {
    const node = makeDo({
      frame_type: 2,
      children: [makeDa('Oper', '', [
        { bda_name: 'ctlVal', bda_path: 'Oper.ctlVal', fc: 'CO', point_code: 'GGIO1.Value1.Oper.ctlVal', value: '', status: '' },
      ])],
    })

    expect(resolveDoReadPointCode(node)).toBe('GGIO1.Value1.Oper.ctlVal')
  })

  it('keeps the read button for unknown frame types when a value point exists', () => {
    const node = makeDo({ children: [makeDa('stVal', 'GGIO1.Value1.stVal')] })

    expect(resolveDoReadPointCode(node)).toBe('GGIO1.Value1.stVal')
  })

  it('does not use q or t metadata as the DO value point', () => {
    const node = makeDo({
      children: [makeDa('q', 'GGIO1.Value1.q'), makeDa('t', 'GGIO1.Value1.t')],
    })

    expect(resolveDoReadPointCode(node)).toBe('')
  })
})
