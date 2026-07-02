import { useState, useEffect, useRef, Children } from 'react'
import { useNavigate } from 'react-router-dom'
import { initGA, trackEvent } from '../../lib/analytics'
import './landing.css'

/* ── prefers-reduced-motion helper ── */
const prefersReduced = () =>
  typeof window !== 'undefined' &&
  window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

/* ── Animated score ring (ATS emerald / Pursuit violet) ── */
function Ring({ v = 70, c = 'emerald', mini = false }) {
  const ref = useRef(null)
  const size = mini ? 30 : 38
  const r = mini ? 12 : 16
  const cx = size / 2
  const circ = 2 * Math.PI * r
  const stroke = c === 'violet' ? 'var(--violet)' : 'var(--emerald)'

  useEffect(() => {
    const el = ref.current
    const rc = el && el.querySelector('.rc')
    if (!rc) return
    if (prefersReduced()) { rc.style.strokeDashoffset = circ * (1 - v / 100); return }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          rc.style.transition = 'stroke-dashoffset .9s ease'
          rc.style.strokeDashoffset = circ * (1 - v / 100)
          io.disconnect()
        }
      })
    })
    io.observe(el)
    return () => io.disconnect()
  }, [v, circ])

  return (
    <span ref={ref} className={mini ? 'miniring' : 'ring'}>
      <svg width={size} height={size}>
        <circle cx={cx} cy={cx} r={r} fill="none" stroke="#eef2f7" strokeWidth="3.5" />
        <circle className="rc" cx={cx} cy={cx} r={r} fill="none" stroke={stroke} strokeWidth="3.5"
          strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={circ} />
      </svg>
      <span className="num">{v}</span>
    </span>
  )
}

/* ── Auto-rotating panel (pauses off-screen + honours reduced motion) ── */
function useRotator(count, delay = 0, interval = 3800) {
  const ref = useRef(null)
  const [idx, setIdx] = useState(0)
  useEffect(() => {
    if (count <= 1 || prefersReduced()) return
    let visible = true
    const el = ref.current
    const io = el ? new IntersectionObserver(
      (es) => es.forEach((e) => { visible = e.isIntersecting }), { threshold: 0.15 }
    ) : null
    if (io && el) io.observe(el)
    let timer = null
    const startTimer = setTimeout(() => {
      timer = setInterval(() => { if (visible) setIdx((i) => (i + 1) % count) }, interval)
    }, delay)
    return () => { clearTimeout(startTimer); if (timer) clearInterval(timer); if (io) io.disconnect() }
  }, [count, delay, interval])
  return { ref, idx }
}

function Panel({ pttl, delay = 0, children }) {
  const slides = Children.toArray(children)
  const { ref, idx } = useRotator(slides.length, delay)
  return (
    <div className="panel">
      <div className="panel-bar">
        <i style={{ background: '#ff5f57' }} /><i style={{ background: '#febc2e' }} /><i style={{ background: '#28c840' }} />
        <span className="pttl">{pttl}</span>
        <span className="dots">{slides.map((_, i) => <b key={i} className={i === idx ? 'on' : ''} />)}</span>
      </div>
      <div className="rotator" ref={ref}>
        {slides.map((s, i) => <div key={i} className={'slide' + (i === idx ? ' active' : '')}>{s}</div>)}
      </div>
    </div>
  )
}

/* ── Data ── */
const PERSONAS = [
  { i: 'P', c: '#10b981', name: 'Praveen', role: 'Head of Product', route: 'Bengaluru → Amsterdam', pain: 'One CV, four markets — which EU roles will actually shortlist me?', s: [88, 81] },
  { i: 'N', c: '#7c6cf5', name: 'Neha', role: 'Strategy Consultant', route: 'Chennai → Luxembourg', pain: 'Consulting travels well — but which EU firms will even see my CV?', s: [84, 90] },
  { i: 'R', c: '#f59e0b', name: 'Rohit', role: 'Finance Director', route: 'Delhi → Dubai', pain: 'Strong on paper, silently filtered out by ATS every time.', s: [79, 86] },
  { i: 'M', c: '#f43f5e', name: 'Meera', role: 'Head of Operations', route: 'Pune → Netherlands', pain: 'Rewriting my CV from scratch for every job, scared of overclaiming.', s: [82, 77] },
  { i: 'A', c: '#4338ca', name: 'Arjun', role: 'Engineering Lead', route: 'Hyderabad → EU', pain: 'Great roles buried across boards and inboxes — nothing tracks them.', s: [85, 80] },
]

const FAQS = [
  { q: 'Will it invent things on my CV?', a: "No. Tailoring only reorders and rephrases what's already in your CV. A factual-integrity score checks every line against your original — anything not traceable is flagged before you send. It changes how your experience is presented, never what you've done." },
  { q: 'Which roles and markets does it cover?', a: 'Senior and leadership roles across every field — product, marketing, finance, operations, engineering, consulting and beyond — in whatever markets you’re targeting, with strong coverage across the EU, the Gulf, Southeast Asia and India.' },
  { q: "What does the ₹500/mo include, and what's BYOK?", a: '₹500/mo is full platform access — scoring, tailoring, cover letters, scanning and tracking. AI compute runs on your own Claude key, so you pay Anthropic directly at cost. We never mark up your AI usage.' },
  { q: 'Do I need an invite to join?', a: "No. You can subscribe directly for ₹500/mo. If someone's shared an invite key with you, redeem it for your first 30 days free instead." },
  { q: 'Is reading my Gmail safe?', a: "It's opt-in and reads only job-alert emails — best set up with a dedicated job-search Gmail so your personal inbox is never touched. You can disconnect at any time, and your data is exportable and deletable." },
  { q: 'Can I cancel anytime?', a: 'Yes — cancel whenever you like and you keep access until the end of the billing month. Your Claude key always remains yours.' },
]

const CHAT_RULES = [
  { re: /pric|byok|key|markup|cost|₹|500|pay|subscri/i, a: '₹500/month for full platform access, cancel anytime. AI runs on your own Claude key — you pay Anthropic directly at cost, no markup. An invite key gives your first 30 days free.' },
  { re: /invent|honest|lie|fabricat|integr|true|real/i, a: 'It never invents anything. Tailoring only reorders and rephrases what’s already in your CV, and a factual-integrity score checks every line against your original before you send.' },
  { re: /gmail|inbox|email|poll|alert/i, a: 'Best practice: make a dedicated job-search Gmail, point all your job alerts at it, and connect it (opt-in, revocable). AIJobsHunt polls it hourly, reads only those alerts, scores each role and adds it to your tracker — ~63% of jobs arrive this way.' },
  { re: /market|countr|region|where|role|field|domain/i, a: 'Senior and leadership roles across every field — product, marketing, finance, operations, engineering, consulting and beyond — in whatever markets you target, with strong EU / Gulf / SE-Asia / India coverage.' },
  { re: /invite|redeem|free|code/i, a: 'An invite key is single-use and gives you 30 days free with full access, no card needed. Enter it during signup. When the month ends you can subscribe for ₹500/mo or request an extension.' },
  { re: /cancel|refund|stop/i, a: 'Cancel anytime and keep access until the end of your billing month. Your Claude key always stays yours.' },
  { re: /score|ats|pursuit/i, a: 'Every role gets two scores: an ATS match (will a tracking system shortlist you?) and a Pursuit score (is it worth your time?). Together they turn a long list into a short one.' },
]
const chatAnswer = (q) => (CHAT_RULES.find((r) => r.re.test(q)) || { a: 'Good question — take a look at the sections above for pricing, honesty, Gmail and invite details, or get access to try it.' }).a

const Check = () => (
  <svg width="18" height="18" fill="none" strokeWidth="2.4" viewBox="0 0 24 24"><path d="m5 13 4 4L19 7" /></svg>
)

export default function LandingPage() {
  const navigate = useNavigate()
  const rootRef = useRef(null)
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [personaIdx, setPersonaIdx] = useState(0)
  const personaRef = useRef(null)
  const [openFaq, setOpenFaq] = useState(-1)

  // chat
  const [chatOpen, setChatOpen] = useState(false)
  const [messages, setMessages] = useState([
    { who: 'bot', text: 'Hi 👋 Ask me about how it works, pricing, BYOK, Gmail polling, or invite keys.' },
  ])
  const [chatInput, setChatInput] = useState('')
  const chatLogRef = useRef(null)

  // invite key
  const [keyVal, setKeyVal] = useState('')

  useEffect(() => { initGA(); document.title = 'AIJobsHunt — AI CV tailoring & ATS scoring, without inventing a thing' }, [])

  // nav shrink/solidify
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 120)
    window.addEventListener('scroll', onScroll, { passive: true }); onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // reveal-on-scroll
  useEffect(() => {
    const root = rootRef.current; if (!root) return
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) }
    }), { threshold: 0.1 })
    root.querySelectorAll('.reveal').forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])

  // persona rotation (pause off-screen + reduced motion)
  useEffect(() => {
    if (prefersReduced()) return
    let visible = true
    const el = personaRef.current
    const io = el ? new IntersectionObserver((es) => es.forEach((e) => { visible = e.isIntersecting }), { threshold: 0.2 }) : null
    if (io && el) io.observe(el)
    const t = setInterval(() => { if (visible) setPersonaIdx((i) => (i + 1) % PERSONAS.length) }, 4200)
    return () => { clearInterval(t); if (io) io.disconnect() }
  }, [])

  // menu: close on Esc
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e) => { if (e.key === 'Escape') setMenuOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  useEffect(() => {
    if (chatLogRef.current) chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight
  }, [messages])

  const goto = (path, event) => (e) => { e.preventDefault(); setMenuOpen(false); if (event) trackEvent(event); navigate(path) }

  const redeem = (e) => {
    e.preventDefault()
    trackEvent('pricing_redeem_click')
    const k = keyVal.trim().toUpperCase()
    if (k) sessionStorage.setItem('pendingInviteKey', k)   // Onboarding prefills the key
    navigate('/register')
  }

  const sendChat = (text) => {
    const t = (text ?? chatInput).trim(); if (!t) return
    setMessages((m) => [...m, { who: 'me', text: t }])
    setChatInput('')
    trackEvent('chat_question', { q: t })
    setTimeout(() => setMessages((m) => [...m, { who: 'bot', text: chatAnswer(t) }]), 340)
  }

  return (
    <div className="aijh" ref={rootRef} id="top">
      {/* NAV */}
      <header className={'nav' + (scrolled ? ' scrolled' : '')}>
        <div className="wrap nav-inner">
          <a href="#top" className="brand"><span className="logo">JH</span><span>AIJobsHunt<small>AI job co-pilot</small></span></a>
          <nav className="nav-links" aria-label="Primary">
            <a href="#how">How it works</a>
            <a href="#why">Why it's different</a>
            <a href="#gmail">Inbox</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
          </nav>
          <div className="nav-cta">
            <a href="/login" className="btn btn-ghost" onClick={goto('/login', 'nav_login_click')}>Log in</a>
            <a href="/register" className="btn btn-primary" onClick={goto('/register', 'nav_getaccess_click')}>Get access</a>
            <button className="hamburger" aria-label="Open menu" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
            </button>
          </div>
        </div>
      </header>

      {/* MOBILE MENU */}
      <div className={'mobile-menu' + (menuOpen ? ' open' : '')} role="dialog" aria-modal="true" aria-label="Menu">
        <div className="mm-scrim" onClick={() => setMenuOpen(false)} />
        <div className="mm-panel">
          <button className="mm-close" aria-label="Close menu" onClick={() => setMenuOpen(false)}>&times;</button>
          <a href="#how" onClick={() => setMenuOpen(false)}>How it works</a>
          <a href="#why" onClick={() => setMenuOpen(false)}>Why it's different</a>
          <a href="#gmail" onClick={() => setMenuOpen(false)}>Inbox</a>
          <a href="#pricing" onClick={() => setMenuOpen(false)}>Pricing</a>
          <a href="#faq" onClick={() => setMenuOpen(false)}>FAQ</a>
          <a href="/login" className="btn btn-ghost" onClick={goto('/login', 'nav_login_click')}>Log in</a>
          <a href="/register" className="btn btn-primary" onClick={goto('/register', 'nav_getaccess_click')}>Get access</a>
        </div>
      </div>

      <main>
        {/* HERO */}
        <section className="hero">
          <div className="wrap hero-grid">
            <div className="reveal in">
              <span className="eyebrow"><span className="dot" />Any field · Any market</span>
              <h1>Tailor your CV to each job's keywords —<br /><span className="u">without inventing a thing.</span></h1>
              <p className="lede">AIJobsHunt finds roles across every field, scores how well you fit each one, and tailors your CV to match — using only what's already true about you.</p>
              <div className="hero-cta">
                <a href="/register" className="btn btn-primary btn-lg" onClick={goto('/register', 'hero_getaccess_click')}>Get access →</a>
                <a href="#how" className="btn btn-ghost btn-lg" onClick={() => trackEvent('hero_howitworks_click')}>See how it works</a>
              </div>
              <p className="access-note"><span className="dot" />₹500/mo platform · your own Claude key, at cost · invite key = 30 days free</p>

              {/* rotating personas */}
              <div className="persona-wrap" ref={personaRef}>
                {PERSONAS.map((p, idx) => (
                  <div key={p.name} className={'persona' + (idx === personaIdx ? ' active' : '')}>
                    <div className="avt" style={{ background: `linear-gradient(135deg,${p.c},rgba(0,0,0,.15))` }}>
                      <svg viewBox="0 0 44 44" width="44" height="44"><circle cx="22" cy="16" r="7" fill="rgba(255,255,255,.9)" /><path d="M8 40c0-8 6.3-13 14-13s14 5 14 13" fill="rgba(255,255,255,.9)" /></svg>
                    </div>
                    <div className="pinfo">
                      <div className="pname">{p.name} <span className="role">· {p.role}</span></div>
                      <div className="route">{p.route}</div>
                      <div className="pain">"{p.pain}"</div>
                    </div>
                    <div className="pscore"><Ring v={p.s[0]} c="emerald" /><Ring v={p.s[1]} c="violet" /></div>
                  </div>
                ))}
              </div>
            </div>

            {/* hero dashboard mock */}
            <div className="reveal in mock" aria-hidden="true">
              <div className="mock-bar">
                <i style={{ background: '#ff5f57' }} /><i style={{ background: '#febc2e' }} /><i style={{ background: '#28c840' }} />
                <span className="mock-url">aijobshunt.com/dashboard</span>
              </div>
              <div className="mock-body">
                <div className="mock-head"><span className="mock-title">Your job search</span><span className="chip on">All jobs · 214</span></div>
                <div className="chips">
                  <span className="chip on">Head of Product</span><span className="chip">VP Marketing</span><span className="chip">Remote</span><span className="chip">Score ≥ 80</span>
                </div>
                <div className="jobrow">
                  <div className="jr-left"><span className="jr-role">Head of Product</span><span className="jr-co">Adyen · Amsterdam</span></div>
                  <div className="jr-right"><span className="flag">NL</span><span className="dualpill"><Ring v={88} c="emerald" /><Ring v={81} c="violet" /></span><span className="badge b-applied">Applied</span></div>
                </div>
                <div className="jobrow">
                  <div className="jr-left"><span className="jr-role">VP Marketing</span><span className="jr-co">Grab · Singapore</span></div>
                  <div className="jr-right"><span className="flag">SG</span><span className="dualpill"><Ring v={76} c="emerald" /><Ring v={90} c="violet" /></span><span className="badge b-int">Interview</span></div>
                </div>
                <div className="jobrow">
                  <div className="jr-left"><span className="jr-role">Finance Director</span><span className="jr-co">Careem · Dubai</span></div>
                  <div className="jr-right"><span className="flag">AE</span><span className="dualpill"><Ring v={83} c="emerald" /><Ring v={79} c="violet" /></span><span className="badge b-new">New</span></div>
                </div>
                <p style={{ fontFamily: 'var(--mono)', fontSize: '10px', color: 'var(--slate-400)', textAlign: 'center', marginTop: '10px' }}>ATS match &nbsp;·&nbsp; Pursuit score</p>
              </div>
            </div>
          </div>
        </section>

        {/* WHO FOR */}
        <section className="section tight">
          <div className="wrap reveal">
            <div className="band">
              <div className="roles">Built for senior &amp; leadership roles across <span>every field</span> — product, marketing, finance, operations, engineering, consulting and beyond.</div>
              <div className="markets"><span className="mkt">EU</span><span className="mkt">Gulf</span><span className="mkt">SE Asia</span><span className="mkt">India</span><span className="mkt">+ wherever you're searching</span></div>
            </div>
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section className="section" id="how">
          <div className="wrap">
            <div className="sec-head reveal">
              <div className="kicker">How it works</div>
              <h2>From job posting to sent application — five steps.</h2>
              <p>AIJobsHunt does the mechanical work of a job search. You take over the moment a recruiter replies.</p>
            </div>
            <div className="steps reveal">
              <div className="step"><div className="ic"><svg viewBox="0 0 24 24" fill="none" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg></div><div className="n" /><h3>Find</h3><p>Pulls roles from job boards, company pages and your inbox — deduped into one list.</p></div>
              <div className="step"><div className="ic"><svg viewBox="0 0 24 24" fill="none" strokeWidth="2"><path d="M3 3v18h18" /><path d="m7 15 4-4 3 3 5-6" /></svg></div><div className="n" /><h3>Score</h3><p>Two scores per role: an <b>ATS match</b> and a <b>Pursuit score</b> — will it shortlist you, and is it worth your time?</p></div>
              <div className="step"><div className="ic"><svg viewBox="0 0 24 24" fill="none" strokeWidth="2"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg></div><div className="n" /><h3>Tailor</h3><p>Reworks your CV for the role — reordering and rephrasing. Never inventing experience, metrics or skills.</p></div>
              <div className="step"><div className="ic"><svg viewBox="0 0 24 24" fill="none" strokeWidth="2"><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></svg></div><div className="n" /><h3>Apply</h3><p>Generates a tailored CV, cover letter and short email — then sends it, or hands you the portal link.</p></div>
              <div className="step"><div className="ic"><svg viewBox="0 0 24 24" fill="none" strokeWidth="2"><path d="M12 8v4l3 2" /><circle cx="12" cy="12" r="9" /></svg></div><div className="n" /><h3>Track</h3><p>Follows each application through interview, offer or rejection — so nothing slips.</p></div>
            </div>
          </div>
        </section>

        {/* WHY DIFFERENT */}
        <section className="section" id="why" style={{ background: 'linear-gradient(180deg,transparent,rgba(16,185,129,.04))' }}>
          <div className="wrap">
            <div className="sec-head reveal">
              <div className="kicker">Why it's different</div>
              <h2>Most AI résumé tools make things up. This one can't.</h2>
              <p>Two ideas do the heavy lifting: score before you spend effort, and tailor without ever fabricating.</p>
            </div>
            <div className="diff reveal">
              <div className="dcard">
                <div className="big"><div className="scorebox">88<small>ATS MATCH</small></div><div className="scorebox v">81<small>PURSUIT</small></div></div>
                <h3>Two scores, not a guess</h3>
                <p>ATS match tells you whether an applicant-tracking system will shortlist you. The Pursuit score tells you whether the role is worth chasing. Together they cut a list of hundreds down to the handful you should act on.</p>
              </div>
              <div className="dcard v">
                <div className="big"><div className="scorebox v">100<small>FACTUAL INTEGRITY</small></div></div>
                <h3>Tailored, never fabricated</h3>
                <p>Every tailored line has to trace back to your real CV. A factual-integrity score checks it mathematically — anything invented drops the number and gets flagged before you send. Your CV changes how it's presented, never what you've done.</p>
              </div>
            </div>
          </div>
        </section>

        {/* SEE IT */}
        <section className="section">
          <div className="wrap">
            <div className="sec-head reveal">
              <div className="kicker">See it with real data</div>
              <h2>What it looks like once it's working for you.</h2>
              <p>Live views from a real search — scored, filtered, tailored and tracked.</p>
            </div>

            {/* TODO(screenshots): these four panels are faithful CSS/SVG mocks of the real
                product. To swap any for a real screenshot, replace the panel body with:
                <img src="/landing/<view>.png" alt="…descriptive alt…" loading="lazy" /> */}
            <div className="seeit reveal">
              {/* TL: Overview / Analytics / Feed */}
              <Panel pttl="dashboard" delay={0}>
                <>
                  <div className="slide-h">Overview <span className="tab">score</span></div>
                  <div className="ov-cards">
                    <div className="ov-card g"><div className="v">61</div><div className="l">Avg Pursuit</div></div>
                    <div className="ov-card a"><div className="v">72</div><div className="l">Avg ATS</div></div>
                    <div className="ov-card i"><div className="v">45</div><div className="l">Apply now</div></div>
                  </div>
                  <div className="readiness">
                    <div className="rh"><b>65%</b><span>Career readiness</span></div>
                    <div className="subm"><span>Keywords (ATS)</span><span>71%</span></div><div className="subbar"><i style={{ width: '71%', background: 'var(--amber)' }} /></div>
                    <div className="subm" style={{ marginTop: '7px' }}><span>Skills (ATS)</span><span>66%</span></div><div className="subbar"><i style={{ width: '66%', background: 'var(--emerald)' }} /></div>
                    <div className="subm" style={{ marginTop: '7px' }}><span>Career fit (Pursuit)</span><span>55%</span></div><div className="subbar"><i style={{ width: '55%', background: 'var(--rose)' }} /></div>
                  </div>
                </>
                <>
                  <div className="slide-h">Analytics <span className="tab">insights</span></div>
                  <div className="an-grid">
                    <div>
                      <div className="donut">
                        <svg width="120" height="120" viewBox="0 0 120 120">
                          <circle cx="60" cy="60" r="42" fill="none" stroke="#eef2f7" strokeWidth="16" />
                          <circle cx="60" cy="60" r="42" fill="none" stroke="var(--violet)" strokeWidth="16" strokeDasharray="252" strokeDashoffset="10" transform="rotate(-90 60 60)" />
                          <circle cx="60" cy="60" r="42" fill="none" stroke="var(--amber)" strokeWidth="16" strokeDasharray="264" strokeDashoffset="257" transform="rotate(-90 60 60)" />
                        </svg>
                      </div>
                      <div className="dm-legend">New 467 · Applied 8</div>
                    </div>
                    <div style={{ alignSelf: 'center' }}>
                      <div style={{ fontFamily: 'var(--mono)', fontSize: '10px', color: 'var(--slate-400)', textTransform: 'uppercase', marginBottom: '8px' }}>Jobs by domain</div>
                      <div className="dombar"><div className="dl"><span>AI &amp; Data</span><b>109</b></div><div className="subbar"><i style={{ width: '100%', background: 'var(--emerald)' }} /></div></div>
                      <div className="dombar"><div className="dl"><span>Supply Chain</span><b>23</b></div><div className="subbar"><i style={{ width: '40%', background: 'var(--emerald)' }} /></div></div>
                      <div className="dombar"><div className="dl"><span>eCommerce</span><b>19</b></div><div className="subbar"><i style={{ width: '33%', background: 'var(--emerald)' }} /></div></div>
                      <div className="dombar"><div className="dl"><span>Fintech</span><b>4</b></div><div className="subbar"><i style={{ width: '12%', background: 'var(--emerald)' }} /></div></div>
                    </div>
                  </div>
                </>
                <>
                  <div className="slide-h">Feed performance <span className="tab">feeds</span></div>
                  <div className="frow"><span className="fn">D1-IN-AI-LinkedIn</span><span className="tag apify">Apify</span><span className="qb"><i style={{ width: '65%', background: 'var(--amber)' }} /></span></div>
                  <div className="frow"><span className="fn">D2-SG-SCM-LinkedIn</span><span className="tag apify">Apify</span><span className="qb"><i style={{ width: '61%', background: 'var(--amber)' }} /></span></div>
                  <div className="frow"><span className="fn">AI &amp; Data — Netherlands</span><span className="tag rss">RSS</span><span className="qb"><i style={{ width: '63%', background: 'var(--amber)' }} /></span></div>
                  <div className="frow"><span className="fn">D1-DE-AI-LinkedIn</span><span className="tag apify">Apify</span><span className="qb"><i style={{ width: '57%', background: 'var(--rose)' }} /></span></div>
                  <div className="frow"><span className="fn">Google Jobs</span><span className="tag apify">Apify</span><span className="qb"><i style={{ width: '64%', background: 'var(--amber)' }} /></span></div>
                  <div className="frow"><span className="fn">D1-LUX-AI-LinkedIn</span><span className="tag apify">Apify</span><span className="qb"><i style={{ width: '46%', background: 'var(--rose)' }} /></span></div>
                </>
              </Panel>

              {/* TR: Jobs table / Add job */}
              <Panel pttl="jobs" delay={950}>
                <>
                  <div className="slide-h">Jobs · 475 <span className="tab">tracker</span></div>
                  <div className="jt-row h"><span>Company / role</span><span>Mkt</span><span>Match</span><span>Fit</span><span /></div>
                  {[
                    ['Garena', 'AI Product Manager', 'SG', 95, 82],
                    ['Lenskart', 'Product@Lenskart', 'IN', 93, 93],
                    ['Crypto.com', 'Senior PM, AI', 'SG', 93, 88],
                    ['RealManage', 'SVP / Head of Product', 'EU', 93, 81],
                    ['Instacart', 'Senior PM, Agentic', 'EU', 90, 94],
                  ].map(([co, role, mkt, m, f]) => (
                    <div className="jt-row" key={co}>
                      <span className="jt-co"><b>{co}</b><span>{role}</span></span>
                      <span className="flag">{mkt}</span>
                      <Ring v={m} c="emerald" mini />
                      <Ring v={f} c="emerald" mini />
                      <span style={{ fontSize: '10px', color: 'var(--emerald-deep)', fontWeight: 600 }}>Tailor →</span>
                    </div>
                  ))}
                </>
                <>
                  <div className="slide-h">Add job <span className="tab">input</span></div>
                  <div className="addjob">
                    <div className="aj-tabs"><span className="aj-tab on">Paste JD</span><span className="aj-tab">From URL</span><span className="aj-tab">Upload file</span></div>
                    <div className="aj-area">Paste the full job description here…</div>
                    <div className="aj-foot"><span className="cancel">Cancel</span><span className="btn btn-primary" style={{ padding: '8px 14px', fontSize: '12px' }}>Parse &amp; score →</span></div>
                  </div>
                  <p style={{ fontSize: '11px', color: 'var(--slate-400)', textAlign: 'center', marginTop: '14px' }}>Scored on both ATS &amp; Pursuit in seconds.</p>
                </>
              </Panel>

              {/* BL: Tailored CV / Cover Letter / Email */}
              <Panel pttl="tailor" delay={1900}>
                <>
                  <div className="slide-h">Tailored CV — change log <span className="tab">6 changes</span></div>
                  <div className="cl-entry"><span className="cl-tag k">KEYWORD INJECTION</span><span className="cl-ok">✓ approved</span><div className="cl-old">Product &amp; Business Leader driving digital product transformations…</div><div className="cl-new">Product &amp; Business Leader shipping AI-powered products from 0 to 1 through hands-on prototyping…</div></div>
                  <div className="cl-entry"><span className="cl-tag r">REPHRASE</span><span className="cl-ok">✓ approved</span><div className="cl-old">Designed an agentic AI ingestion system…</div><div className="cl-new">Owned end-to-end delivery of an agentic AI ingestion system from discovery to production…</div></div>
                  <div className="integrity"><b>100</b> Factual integrity — every line traces to your master CV. Nothing invented.</div>
                </>
                <>
                  <div className="slide-h">Cover Letter <span className="tab">story-led</span></div>
                  <div className="doc">
                    <p><b>Dear Hiring Team,</b></p>
                    <p>When our marketplace faced a revenue leak from lost claims, I didn't write a spec — I prototyped a solution, shipped it in weeks, and automated the recovery workflow.</p>
                    <p>I'm applying because the role sits at the intersection of what I've built and what energizes me most: taking products to production with hands-on ownership…</p>
                    <p><b>Warm regards</b></p>
                  </div>
                </>
                <>
                  <div className="slide-h">Email Draft <span className="tab">ready</span></div>
                  <div className="testmode">🟠 Test mode ON — email routes to your notification address, not the recruiter.</div>
                  <div className="field"><div className="fl">Subject</div><div className="fv">Application: AI Product Manager — Garena</div></div>
                  <div className="field"><div className="fl">Attachments</div><div className="fv">CV.pdf · CoverLetter.pdf</div></div>
                  <div className="field"><div className="fl">Body</div><div className="fv" style={{ color: 'var(--slate-500)' }}>Dear Hiring Team, I'm applying for the AI Product Manager role…</div></div>
                </>
              </Panel>

              {/* BR: Feeds / Companies / Scan history */}
              <Panel pttl="feeds & scanning" delay={2850}>
                <>
                  <div className="slide-h">RSS &amp; Apify feeds <span className="tab">sources</span></div>
                  <div className="frow"><span className="tog" /><span className="fn">LinkedIn Jobs</span><span className="tag apify">Apify</span><span className="btn btn-ghost" style={{ padding: '3px 10px', fontSize: '10px', minHeight: 'auto' }}>Run</span></div>
                  <div className="frow"><span className="tog" /><span className="fn">Google Jobs</span><span className="tag apify">Apify</span><span className="btn btn-ghost" style={{ padding: '3px 10px', fontSize: '10px', minHeight: 'auto' }}>Run</span></div>
                  <div className="frow"><span className="tog" /><span className="fn">Jobicy NL</span><span className="tag rss">RSS</span><span className="btn btn-ghost" style={{ padding: '3px 10px', fontSize: '10px', minHeight: 'auto' }}>Run</span></div>
                  <div className="frow"><span className="tog" /><span className="fn">AI &amp; Data Leadership — NL</span><span className="tag rss">RSS</span><span className="btn btn-ghost" style={{ padding: '3px 10px', fontSize: '10px', minHeight: 'auto' }}>Run</span></div>
                  <div className="frow"><span className="tog" /><span className="fn">D4-LUX-Fin-LinkedIn</span><span className="tag apify">Apify</span><span className="btn btn-ghost" style={{ padding: '3px 10px', fontSize: '10px', minHeight: 'auto' }}>Run</span></div>
                </>
                <>
                  <div className="slide-h">Target companies · 23 <span className="tab">tracked</span></div>
                  <div className="cg">
                    <div className="cg-card"><b>Careem</b><span>Dubai · Careers →</span></div>
                    <div className="cg-card"><b>Adyen</b><span>NL · Careers →</span></div>
                    <div className="cg-card"><b>Grab</b><span>SG · Careers →</span></div>
                    <div className="cg-card"><b>Meesho</b><span>IN · Careers →</span></div>
                    <div className="cg-card"><b>Databricks</b><span>EU · Careers →</span></div>
                    <div className="cg-card"><b>Razorpay</b><span>IN · Careers →</span></div>
                  </div>
                </>
                <>
                  <div className="slide-h">Scan history <span className="tab">runs</span></div>
                  <div className="sh-row"><span className="st ok">success</span><span style={{ color: 'var(--slate-500)' }}>Jul 3 · 530s</span><span>286 found</span><span style={{ color: 'var(--emerald-deep)', fontWeight: 600 }}>0 added</span></div>
                  <div className="sh-row"><span className="st ok">success</span><span style={{ color: 'var(--slate-500)' }}>Jun 30 · 512s</span><span>267 found</span><span style={{ color: 'var(--emerald-deep)', fontWeight: 600 }}>0 added</span></div>
                  <div className="sh-row"><span className="st ok">success</span><span style={{ color: 'var(--slate-500)' }}>Jun 26 · 1952s</span><span>292 found</span><span style={{ color: 'var(--emerald-deep)', fontWeight: 600 }}>124 added</span></div>
                  <div className="sh-row"><span className="st ok">success</span><span style={{ color: 'var(--slate-500)' }}>Jun 24 · 588s</span><span>79 found</span><span style={{ color: 'var(--emerald-deep)', fontWeight: 600 }}>51 added</span></div>
                  <div className="sh-row"><span className="st part">partial</span><span style={{ color: 'var(--slate-500)' }}>Jun 24 · 76s</span><span>0 found</span><span style={{ color: 'var(--slate-400)' }}>0 added</span></div>
                </>
              </Panel>
            </div>
            <p style={{ textAlign: 'center', fontSize: '12.5px', color: 'var(--slate-400)', marginTop: '20px' }}>Panels auto-rotate · representative live data</p>
          </div>
        </section>

        {/* GMAIL BLOCK */}
        <section className="section" id="gmail" style={{ background: 'linear-gradient(180deg,transparent,rgba(124,108,245,.04))' }}>
          <div className="wrap">
            <div className="gmail-grid reveal">
              <div>
                <span className="privacy-strip">🔒 opt-in · reads only job alerts · revocable anytime</span>
                <div className="kicker">Inbox polling</div>
                <h2 style={{ marginBottom: '14px' }}>Your inbox is already full of jobs.</h2>
                <p style={{ fontSize: '16px', color: 'var(--slate-700)', marginBottom: '24px' }}>Create one Gmail just for the hunt. Point every job alert at it. AIJobsHunt polls it hourly, reads only those alerts, scores each role, and drops it into your tracker — your personal inbox stays private and clean.</p>
                <ul className="bp">
                  <li><span className="k">1</span><div><b>Make a job-only Gmail</b><p>Subscriptions flood it — not your personal inbox. Your privacy stays in your real mailbox.</p></div></li>
                  <li><span className="k">2</span><div><b>Send every alert there</b><p>Tune LinkedIn, Indeed and company alerts to your roles and markets.</p></div></li>
                  <li><span className="k">3</span><div><b>Connect it — opt-in, revocable</b><p>An app password, encrypted. It reads job alerts, never your personal mail.</p></div></li>
                  <li><span className="k">4</span><div><b>Check your tracker, not your inbox</b><p>Hourly polling means scored jobs come to you.</p></div></li>
                  <li><span className="k">5</span><div><b>Forward strays with "jh:"</b><p>A referral or newsletter? Forward it with a "jh:" subject and it's fetched, scored and saved.</p></div></li>
                </ul>
              </div>
              <div>
                <div className="funnel">
                  <div style={{ fontFamily: 'var(--mono)', fontSize: '10.5px', color: 'var(--slate-400)', textTransform: 'uppercase', marginBottom: '6px' }}>Last 7 days</div>
                  <div className="funnel-stat">
                    <div className="fs"><b>50</b><span>emails</span></div><div className="arrow">→</div>
                    <div className="fs"><b>366</b><span>links found</span></div><div className="arrow">→</div>
                    <div className="fs"><b>183</b><span>jobs saved</span></div>
                  </div>
                  <div className="mail-card">
                    <div className="mc-l"><b>Principal Product Owner, AI Enablement</b><span>linkedin.com · 6 hours ago</span><div className="brk"><span>10 links</span><span>10 gated</span><span className="g">6 saved</span></div></div>
                    <span className="saved">6 saved</span>
                  </div>
                  <div className="mail-card">
                    <div className="mc-l"><b>Head of IT Ecommerce at Dyson</b><span>linkedin.com · 8 hours ago</span><div className="brk"><span>10 links</span><span>10 gated</span><span className="g">5 saved</span></div></div>
                    <span className="saved">5 saved</span>
                  </div>
                  <div className="mail-card">
                    <div className="mc-l"><b>Deputy CTO (AI Product) at Jobgether</b><span>linkedin.com · 14 hours ago</span><div className="brk"><span>10 links</span><span>10 gated</span><span className="g">6 saved</span></div></div>
                    <span className="saved">6 saved</span>
                  </div>
                  <p style={{ fontSize: '11.5px', color: 'var(--slate-500)', textAlign: 'center', marginTop: '12px' }}><b style={{ color: 'var(--emerald-deep)', fontFamily: 'var(--mono)' }}>63%</b> of tracked jobs arrive via Gmail alerts — hands-free.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* BYOK + TRANSPARENCY */}
        <section className="section">
          <div className="wrap">
            <div className="sec-head center reveal">
              <div className="kicker">Bring your own key</div>
              <h2>Your Claude key. Your costs. No markup.</h2>
              <p>You connect your own Anthropic key. Every token goes to Anthropic at their price — we never sit in the middle of your AI bill.</p>
            </div>
            <div className="trust-grid reveal">
              <div className="byok">
                <h3>No markup, ever</h3>
                <p>The ₹500/mo covers the platform. AI compute runs on your key, paid directly to Anthropic at cost.</p>
                <ul className="bl">
                  <li><Check />Your key — encrypted (AES-256), never shared or logged</li>
                  <li><Check />Pay Anthropic directly — exactly what it costs, no middleman</li>
                  <li><Check />Pick your model — Sonnet, Opus or Haiku, your call</li>
                  <li><Check />Cancel the platform anytime — your key stays yours</li>
                </ul>
              </div>
              <div className="transp">
                <h3>See what every action costs</h3>
                <div className="sub">Real spend, itemised — before and after.</div>
                <div className="usage-split">
                  <div className="usage-box claude"><div className="ub-h"><span>Anthropic (Claude)</span></div><div className="ub-v">₹593</div><div className="ub-s">3.0M tokens · 1,061 calls</div></div>
                  <div className="usage-box apify"><div className="ub-h"><span>Apify (scanning)</span></div><div className="ub-v">₹3.68</div><div className="ub-s">736 runs · your key</div></div>
                </div>
                <div className="costtable">
                  <div className="ct-row h"><span>Typical action</span><span>Cost</span></div>
                  <div className="ct-row"><span>Score a job</span><span className="price">₹0.10</span></div>
                  <div className="ct-row"><span>Tailor a CV</span><span className="price">₹1.30</span></div>
                  <div className="ct-row"><span>Generate domain CV</span><span className="price">₹0.90</span></div>
                  <div className="ct-row"><span>Monthly active search</span><span className="price">~₹15</span></div>
                </div>
                <div className="opt-note">✦ Smart model routing keeps spend low — <b>~99% saved</b> vs naive prompting on background scans.</div>
              </div>
            </div>
          </div>
        </section>

        {/* PRICING */}
        <section className="section" id="pricing">
          <div className="wrap">
            <div className="sec-head reveal">
              <div className="kicker">Pricing</div>
              <h2>One plan. Or a free month on us.</h2>
              <p>A flat platform fee — AI runs on your own key, at cost. No tiers, no add-ons.</p>
            </div>
            <div className="pricing reveal">
              <div className="price-card">
                <div style={{ fontFamily: 'var(--display)', fontWeight: 600, fontSize: '15px', color: 'var(--slate-300)' }}>AIJobsHunt Pro</div>
                <div className="price-tag"><span className="amt">₹500</span><span className="per">/ month</span></div>
                <div className="byok-line">+ your own Claude key, paid to Anthropic at cost</div>
                <div style={{ color: 'var(--slate-400)', fontSize: '13px', marginBottom: '4px' }}>Cancel anytime.</div>
                <ul className="plist">
                  <li><Check />Full platform access — no feature limits</li>
                  <li><Check />Job scoring — ATS + Pursuit</li>
                  <li><Check />CV tailoring with factual-integrity checks</li>
                  <li><Check />Cover letters, application emails &amp; tracking</li>
                  <li><Check />Weekly scans + hourly Gmail polling</li>
                </ul>
                <a href="/register" className="btn btn-white btn-lg" onClick={goto('/register', 'pricing_subscribe_click')}>Subscribe — ₹500/mo</a>
              </div>
              <div className="invite-card">
                <h3>Have an invite key?</h3>
                <p>Redeem it for 30 days free — full access, no card needed. When the month ends, keep going for ₹500/mo or request an extension.</p>
                <form className="keyrow" onSubmit={redeem}>
                  <input value={keyVal} onChange={(e) => setKeyVal(e.target.value.toUpperCase())} placeholder="JH-XXXX-XXXX" maxLength={12} aria-label="Invite key" />
                  <button type="submit" className="btn btn-primary">Redeem</button>
                </form>
                <p className="invite-fine">Single-use key. Redeeming creates your account and starts your free month.</p>
              </div>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="section" id="faq">
          <div className="wrap">
            <div className="sec-head reveal">
              <div className="kicker">FAQ</div>
              <h2>Questions, answered.</h2>
              <p>Still unsure? Ask the chat in the corner — no login needed.</p>
            </div>
            <div className="faq reveal">
              {FAQS.map((f, i) => (
                <div className={'qa' + (openFaq === i ? ' open' : '')} key={i}>
                  <button aria-expanded={openFaq === i} onClick={() => setOpenFaq(openFaq === i ? -1 : i)}>
                    {f.q}<span className="plus" />
                  </button>
                  <div className="ans" style={{ maxHeight: openFaq === i ? '240px' : 0 }}><p>{f.a}</p></div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FINALE */}
        <section className="section">
          <div className="wrap reveal">
            <div className="finale">
              <h2>Stop searching. Start shortlisting.</h2>
              <p>Give AIJobsHunt your CV and let it score, tailor and track — while you focus on the conversations that matter.</p>
              <a href="/register" className="btn btn-white btn-lg" onClick={goto('/register', 'finale_getaccess_click')}>Get access →</a>
            </div>
          </div>
        </section>
      </main>

      {/* FOOTER */}
      <footer>
        <div className="wrap">
          <div className="foot">
            <div>
              <a href="#top" className="brand"><span className="logo">JH</span><span>AIJobsHunt</span></a>
              <p>The AI job co-pilot for your next role. Scored, tailored, tracked — honestly.</p>
            </div>
            <div className="foot-links">
              <div className="foot-col"><b>Product</b><a href="#how">How it works</a><a href="#why">Why it's different</a><a href="#gmail">Inbox polling</a><a href="#pricing">Pricing</a><a href="#faq">FAQ</a></div>
              <div className="foot-col"><b>Account</b><a href="/login" onClick={goto('/login', 'footer_login_click')}>Log in</a><a href="/register" onClick={goto('/register', 'footer_signup_click')}>Get access</a></div>
              <div className="foot-col"><b>Legal</b><a href="https://praveenp1118.github.io/JobHunt/privacy.html">Privacy Policy</a><a href="https://praveenp1118.github.io/JobHunt/terms.html">Terms of Service</a><a href="https://praveenp1118.github.io/JobHunt/cookies.html">Cookie Policy</a></div>
              <div className="foot-col"><b>Contact</b><a href="mailto:support@aijobshunt.com">support@aijobshunt.com</a></div>
            </div>
          </div>
          <div className="foot-bottom">
            <span>© 2026 AIJobsHunt. All rights reserved.</span>
            <span>This site uses Google Analytics to understand how visitors use it.</span>
          </div>
        </div>
      </footer>

      {/* CHAT */}
      <button className="chat-fab" aria-label="Open chat" onClick={() => { setChatOpen((o) => !o); trackEvent('chat_open') }}>
        <svg width="18" height="18" fill="none" stroke="#fff" strokeWidth="2" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
        Questions?
      </button>
      <div className={'chat-panel' + (chatOpen ? ' open' : '')}>
        <div className="chat-top"><b>Ask about AIJobsHunt</b><small>No login needed · answers common questions</small></div>
        <div className="chat-log" ref={chatLogRef}>
          {messages.map((m, i) => <div key={i} className={'msg ' + m.who}>{m.text}</div>)}
        </div>
        <div className="chat-suggest">
          <button onClick={() => sendChat('How does pricing and BYOK work?')}>Pricing &amp; BYOK</button>
          <button onClick={() => sendChat('Will it invent things on my CV?')}>Is it honest?</button>
          <button onClick={() => sendChat('How does Gmail polling work?')}>Gmail</button>
          <button onClick={() => sendChat('How do invite keys work?')}>Invite keys</button>
        </div>
        <div className="chat-in">
          <input value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="Type a question…"
            onKeyDown={(e) => { if (e.key === 'Enter') sendChat() }} aria-label="Chat message" />
          <button onClick={() => sendChat()} aria-label="Send">→</button>
        </div>
      </div>
    </div>
  )
}
