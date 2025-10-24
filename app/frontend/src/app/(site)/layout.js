'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from "react";
import { get } from "@/api/api-client";

function Nav({me}) {
  const pathname = usePathname()
  
  const isActive = (href) => {
    // Exact match for home and logout
    if (href === '/' || href === '/logout') {
      return pathname === href ? 'active' : ''
    }
    
    // For other sections, check if current path starts with the href
    // This will highlight parent sections when viewing detail/new pages
    return pathname.startsWith(href) ? 'active' : ''
  }

  return (
    <nav>
      <Link href="/" className={isActive('/')}>Home</Link>
      <Link href="/experiments" className={isActive('/experiments')}>Experiments</Link>
      <Link href="/revisions" className={isActive('/revisions')}>Revisions</Link>
      <Link href="/runs" className={isActive('/runs')}>Runs</Link>
      <Link href="/environments" className={isActive('/environments')}>Environments</Link>
      <Link href="/plugins" className={isActive('/plugins')}>🔌 Plugins</Link>
      {me ? <span style={{ marginLeft: 'auto', padding: '0.5rem' }}>{me.name}</span> : <span style={{ marginLeft: 'auto', padding: '0.5rem' }}>...</span>}
      <Link href="/logout" className={isActive('/logout')}>Logout</Link>
    </nav>
  )
}

export default function SiteLayout({ children }) {
   const [me, setMe] = useState(null);

	useEffect(() => {
		async function getMe(){
		    try {
		      const me = await get("/api/auth/me");
		      setMe(me);
		    } catch (e) { }
		 }
		 getMe();
	  }, []);

  // Server-side middleware now handles authentication redirects
  // Keep client-side token check for UX but don't redirect

  return (
      <>
        <header>
          <Nav me={me} />
        </header>
        <main className="container">{children}</main>
      </>
  );
}