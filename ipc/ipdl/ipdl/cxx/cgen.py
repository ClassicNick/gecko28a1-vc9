# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sys
import os

from ipdl.cgen import CodePrinter
from ipdl.cxx.ast import TypeArray, Visitor

msvcver = int(os.getenv('MOZ_MSVCVERSION', default=10))

class CxxCodeGen(CodePrinter, Visitor):
    def __init__(self, outf=sys.stdout, indentCols=4):
        CodePrinter.__init__(self, outf, indentCols)

    def cgen(self, cxxfile):
        cxxfile.accept(self)

    def visitWhitespace(self, ws):
        if ws.indent:
            self.printdent('')
        self.write(ws.ws)

    def visitCppDirective(self, cd):
        self.println('#%s %s'% (cd.directive, cd.rest))

    def visitNamespace(self, ns):
        self.println('namespace '+ ns.name +' {')
        self.visitBlock(ns)
        self.println('} // namespace '+ ns.name)

    def visitType(self, t):
        if t.const:
            self.write('const ')

        self.write(t.name)

        if t.T is not None:
            self.write('<')
            t.T.accept(self)
            self.write('>')

        ts = ''
        if t.ptr:            ts += '*'
        elif t.ptrconst:     ts += '* const'
        elif t.ptrptr:       ts += '**'
        elif t.ptrconstptr:  ts += '* const*'

        if t.ref:  ts += '&'

        self.write(ts)

    def visitTypeEnum(self, te):
        self.write('enum')
        if te.name:
            self.write(' '+ te.name)
        self.println(' {')

        self.indent()
        nids = len(te.idnums)
        for i, (id, num) in enumerate(te.idnums):
            self.printdent(id)
            if num:
                self.write(' = '+ str(num))
            if i != (nids-1):
                self.write(',')
            self.println()
        self.dedent()
        self.printdent('}')

    def visitTypeUnion(self, u):
        self.write('union')
        if u.name:
            self.write(' '+ u.name)
        self.println(' {')

        self.indent()
        for decl in u.components:
            self.printdent()
            decl.accept(self)
            self.println(';')
        self.dedent()

        self.printdent('}')


    def visitTypedef(self, td):
        self.printdent('typedef ')
        td.fromtype.accept(self)
        self.println(' '+ td.totypename +';')

    def visitUsing(self, us):
        self.printdent('using ')
        us.type.accept(self)
        self.println(';')

    def visitForwardDecl(self, fd):
        if fd.cls:      self.printdent('class ')
        elif fd.struct: self.printdent('struct ')
        self.write(str(fd.pqname))
        self.println(';')

    def visitDecl(self, d):
        # C-syntax arrays make code generation much more annoying
        if isinstance(d.type, TypeArray):
            d.type.basetype.accept(self)
        else:
            d.type.accept(self)

        if d.name:
            self.write(' '+ d.name)

        if isinstance(d.type, TypeArray):
            self.write('[')
            d.type.nmemb.accept(self)
            self.write(']')

    def visitParam(self, p):
        self.visitDecl(p)
        if p.default is not None:
            self.write(' = ')
            p.default.accept(self)

    def visitClass(self, c):
        if c.specializes is not None:
            self.printdentln('template<>')
        
        if c.struct:
            self.printdent('struct')
        else:
            self.printdent('class')
        if c.interface:
            # FIXME/cjones: turn this "on" when we get the analysis
            self.write(' /*NS_INTERFACE_CLASS*/')
        if c.abstract:
            # FIXME/cjones: turn this "on" when we get the analysis
            self.write(' /*NS_ABSTRACT_CLASS*/')
        self.write(' '+ c.name)
        if c.final:
            self.write(' MOZ_FINAL')

        if c.specializes is not None:
            self.write(' <')
            c.specializes.accept(self)
            self.write('>')

        ninh = len(c.inherits)
        if 0 < ninh:
            self.println(' :')
            self.indent()
            for i, inherit in enumerate(c.inherits):
                self.printdent()
                inherit.accept(self)
                if i != (ninh - 1):
                    self.println(',')
            self.dedent()
        self.println()

        self.printdentln('{')
        self.indent()

        self.visitBlock(c)

        self.dedent()
        self.printdentln('};')

    def visitInherit(self, inh):
        self.write(inh.viz +' ')
        inh.type.accept(self)

    def visitFriendClassDecl(self, fcd):
        self.printdentln('friend class '+ fcd.friend +';')


    def visitMethodDecl(self, md):
        assert not (md.static and md.virtual)

        if md.T:
            self.write('template<')
            self.write('typename ')
            md.T.accept(self)
            self.println('>')
            self.printdent()

        if md.inline:
            self.write('inline ')
        if md.inline:
            self.write('MOZ_NEVER_INLINE ')
        if md.static:
            self.write('static ')
        if md.virtual:
            self.write('virtual ')
        if md.ret:
            if md.only_for_definition and msvcver > 9:
                self.write('auto ')
            else:
                md.ret.accept(self)
                self.println()
                self.printdent()
        if md.typeop is not None:
            self.write('operator ')
            md.typeop.accept(self)
        else:
            self.write(md.name)

        self.write('(')
        self.writeDeclList(md.params)
        self.write(')')

        if md.const:
            self.write(' const')
        if md.ret and md.only_for_definition and msvcver > 9:
            self.write(' -> ')
            md.ret.accept(self)
        if md.warn_unused:
            self.write(' NS_WARN_UNUSED_RESULT')
        if md.pure:
            self.write(' = 0')


    def visitMethodDefn(self, md):
        self.printdent()
        md.decl.accept(self)
        self.println()

        self.printdentln('{')
        self.indent()
        self.visitBlock(md)
        self.dedent()
        self.printdentln('}')


    def visitConstructorDecl(self, cd):
        if cd.explicit:
            self.write('explicit ')
        self.visitMethodDecl(cd)

    def visitConstructorDefn(self, cd):
        self.printdent()
        cd.decl.accept(self)
        if len(cd.memberinits):
            self.println(' :')
            self.indent()
            ninits = len(cd.memberinits)
            for i, init in enumerate(cd.memberinits):
                self.printdent()
                init.accept(self)
                if i != (ninits-1):
                    self.println(',')
            self.dedent()
        self.println()

        self.printdentln('{')
        self.indent()

        self.visitBlock(cd)

        self.dedent()
        self.printdentln('}')


    def visitDestructorDecl(self, dd):
        if dd.inline:
            self.write('inline ')
        if dd.virtual:
            self.write('virtual ')

        # hack alert
        parts = dd.name.split('::')
        parts[-1] = '~'+ parts[-1]

        self.write('::'.join(parts) +'()')

    def visitDestructorDefn(self, dd):
        self.printdent()
        dd.decl.accept(self)
        self.println()

        self.printdentln('{')
        self.indent()

        self.visitBlock(dd)

        self.dedent()
        self.printdentln('}')


    def visitExprLiteral(self, el):
        self.write(str(el))

    def visitExprVar(self, ev):
        self.write(ev.name)

    def visitExprPrefixUnop(self, e):
        self.write('(')
        self.write(e.op)
        self.write('(')
        e.expr.accept(self)
        self.write(')')
        self.write(')')

    def visitExprCast(self, c):
        pfx, sfx = '', ''
        if c.dynamic:        pfx, sfx = 'dynamic_cast<', '>'
        elif c.static:       pfx, sfx = 'static_cast<', '>'
        elif c.reinterpret:  pfx, sfx = 'reinterpret_cast<', '>'
        elif c.const:        pfx, sfx = 'const_cast<', '>'
        elif c.C:            pfx, sfx = '(', ')'
        self.write(pfx)
        c.type.accept(self)
        self.write(sfx +'(')
        c.expr.accept(self)
        self.write(')')

    def visitExprBinary(self, e):
        self.write('(')
        e.left.accept(self)
        self.write(') '+ e.op +' (')
        e.right.accept(self)
        self.write(')')

    def visitExprConditional(self, c):
        self.write('(')
        c.cond.accept(self)
        self.write(' ? ')
        c.ife.accept(self)
        self.write(' : ')
        c.elsee.accept(self)
        self.write(')')

    def visitExprIndex(self, ei):
        ei.arr.accept(self)
        self.write('[')
        ei.idx.accept(self)
        self.write(']')

    def visitExprSelect(self, es):
        self.write('(')
        es.obj.accept(self)
        self.write(')')
        self.write(es.op + es.field)

    def visitExprAssn(self, ea):
        ea.lhs.accept(self)
        self.write(' '+ ea.op +' ')
        ea.rhs.accept(self)

    def visitExprCall(self, ec):
        ec.func.accept(self)
        self.write('(')
        self.writeExprList(ec.args)
        self.write(')')

    def visitExprNew(self, en):
        self.write('new ')
        if en.newargs is not None:
            self.write('(')
            self.writeExprList(en.newargs)
            self.write(') ')
        en.ctype.accept(self)
        if en.args is not None:
            self.write('(')
            self.writeExprList(en.args)
            self.write(')')

    def visitExprDelete(self, ed):
        self.write('delete ')
        ed.obj.accept(self)


    def visitStmtBlock(self, b):
        self.printdentln('{')
        self.indent()
        self.visitBlock(b)
        self.dedent()
        self.printdentln('}')

    def visitLabel(self, label):
        self.dedent()           # better not be at global scope ...
        self.printdentln(label.name +':')
        self.indent()

    def visitCaseLabel(self, cl):
        self.dedent()
        self.printdentln('case '+ cl.name +':')
        self.indent()

    def visitDefaultLabel(self, dl):
        self.dedent()
        self.printdentln('default:')
        self.indent()


    def visitStmtIf(self, si):
        self.printdent('if (')
        si.cond.accept(self)
        self.println(') {')
        self.indent()
        si.ifb.accept(self)
        self.dedent()
        self.printdentln('}')

        if si.elseb is not None:
            self.printdentln('else {')
            self.indent()
            si.elseb.accept(self)
            self.dedent()
            self.printdentln('}')


    def visitStmtFor(self, sf):
        self.printdent('for (')
        if sf.init is not None:
            sf.init.accept(self)
        self.write('; ')
        if sf.cond is not None:
            sf.cond.accept(self)
        self.write('; ')
        if sf.update is not None:
            sf.update.accept(self)
        self.println(') {')

        self.indent()
        self.visitBlock(sf)
        self.dedent()
        self.printdentln('}')


    def visitStmtSwitch(self, sw):
        self.printdent('switch (')
        sw.expr.accept(self)
        self.println(') {')
        self.indent()
        self.visitBlock(sw)
        self.dedent()
        self.printdentln('}')

    def visitStmtBreak(self, sb):
        self.printdentln('break;')


    def visitStmtDecl(self, sd):
        self.printdent()
        sd.decl.accept(self)
        if sd.initargs is not None:
            self.write('(')
            self.writeDeclList(sd.initargs)
            self.write(')')
        if sd.init is not None:
            self.write(' = ')
            sd.init.accept(self)
        self.println(';')


    def visitStmtExpr(self, se):
        self.printdent()
        se.expr.accept(self)
        self.println(';')


    def visitStmtReturn(self, sr):
        self.printdent('return')
        if sr.expr:
            self.write (' ')
            sr.expr.accept(self)
        self.println(';')


    def writeDeclList(self, decls):
        # FIXME/cjones: try to do nice formatting of these guys

        ndecls = len(decls)
        if 0 == ndecls:
            return
        elif 1 == ndecls:
            decls[0].accept(self)
            return

        self.indent()
        self.indent()
        for i, decl in enumerate(decls):
            self.println()
            self.printdent()
            decl.accept(self)
            if i != (ndecls-1):
                self.write(',')
        self.dedent()
        self.dedent()

    def writeExprList(self, exprs):
        # FIXME/cjones: try to do nice formatting and share code with
        # writeDeclList()
        nexprs = len(exprs)
        for i, expr in enumerate(exprs):
            expr.accept(self)
            if i != (nexprs-1):
                self.write(', ')
